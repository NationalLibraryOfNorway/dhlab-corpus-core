"""Database access. Everything that knows about SQLite, file names, tables and SQL lives here.

The collection is stored as a set of read-only SQLite files in one directory:

- ``urns.db``      maps every document (``urn_seq`` == dhlabid) to its URN, doctype and shard file
- ``metadata.db``  one metadata row per document, as a plain table and as an FTS5 index
- ``alto_*.db``    shards holding the full text, FTS5 indexes and word counts for a range of documents
- ``grand_total.db`` precomputed word totals for the whole collection

A note on names. The integer identifier of a document, the *dhlabid*, goes by three names in the
databases: ``dhlabid`` in ``metadata.db``, ``urn_seq`` in ``urns.db`` and in the shards' ``ft_doc_metadata``,
and — misleadingly — ``urn`` in the other shard tables (``ft``, ``ft_para``, ``unigram``, ...). The actual URN
(``URN:NBN:no-nb_...``) is the text column ``urn`` of ``urns.db``, ``metadata.db`` and ``ft_doc_metadata``.
This module hides that: everything it takes and returns calls the integer ``dhlabid`` and the text ``urn``.
"""

import sqlite3
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import batched
from pathlib import Path
from typing import Any, Literal

from dhlab_core_api.errors import InvalidQueryError

URNS_DB = "urns.db"
METADATA_DB = "metadata.db"
GRAND_TOTAL_DB = "grand_total.db"

METADATA_COLUMNS = (
    "dhlabid",
    "urn",
    "title",
    "authors",
    "oaiid",
    "sesamid",
    "isbn10",
    "city",
    "timestamp",
    "year",
    "publisher",
    "langs",
    "subjects",
    "ddc",
    "genres",
    "literaryform",
    "doctype",
    "ocr_creator",
    "ocr_timestamp",
)
# The per-shard ``ft_doc_metadata`` index has no OCR columns and calls the dhlabid ``urn_seq``.
FULLTEXT_METADATA_COLUMNS = METADATA_COLUMNS[:-2]

MIN_YEAR = 1500
MAX_YEAR = 2030

# Number of bound parameters per ``IN (...)`` lookup. Well below SQLite's limit.
_LOOKUP_BATCH_SIZE = 900

# Fragments of SQLite error messages that are caused by the user's search expression rather than by us.
_USER_QUERY_ERRORS = ("fts5:", "syntax error", "no such column", "unknown special query", "unterminated string")

type Order = Literal["random", "rank", "first"]
type NgramOperator = Literal["=", "LIKE", ">=", "<="]
type TimeUnit = Literal["year", "timestamp"]


@dataclass(frozen=True)
class MetadataSearch:
    """A metadata search, independent of API version."""

    match: dict[str, str] = field(default_factory=dict)
    """FTS5 query per metadata column, e.g. ``{"authors": "Ibsen"}``."""
    ddc: str | None = None
    """Dewey class. Matches one whole class in the document's list of classes, or an FTS5 prefix query if it has ``*``."""
    year_from: int | None = None
    year_to: int | None = None
    """Inclusive bounds on the year of publication."""
    timestamp_from: int | None = None
    timestamp_to: int | None = None
    """Inclusive bounds on the date of publication (YYYYMMDD)."""
    freetext: str | None = None
    """FTS5 query against all metadata fields."""
    fulltext: str | None = None
    """FTS5 query against the document text. Switches the search to the shards."""
    order: Order = "random"
    limit: int = 10
    seed: int | None = None
    """Makes the ``random`` order reproducible: the same seed gives the same order for the same data."""


@dataclass(frozen=True)
class NgramFilter:
    """A single metadata condition for n-gram aggregation."""

    column: str
    operator: NgramOperator
    value: str | int


@dataclass(frozen=True)
class Document:
    """Where a document lives."""

    dhlabid: int
    urn: str
    shard: str


class CorpusRepository:
    """Read-only access to the collection's SQLite files.

    Holds no connection state — only the directory path and a thread pool — so a single
    instance is safe to share across requests. Connections are opened per call, on the
    calling thread, and closed when the call returns.
    """

    def __init__(self, database_dir: Path, max_workers: int = 8) -> None:
        self._database_dir = database_dir
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="shard")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ plumbing

    def _uri(self, filename: str) -> str:
        return f"{(self._database_dir / filename).resolve().as_uri()}?mode=ro"

    @contextmanager
    def connect(self, filename: str, attach_metadata: bool = False) -> Iterator[sqlite3.Connection]:
        """Open ``<database_dir>/<filename>`` read-only and yield a connection.

        The API only ever queries, so the connection is opened in read-only
        mode: any write raises ``sqlite3.OperationalError``.
        """
        connection = sqlite3.connect(self._uri(filename), uri=True)
        try:
            if attach_metadata:
                connection.execute("ATTACH DATABASE ? AS meta", (self._uri(METADATA_DB),))
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _execute_user_query(connection: sqlite3.Connection, sql: str, params: Sequence[Any]) -> list[tuple]:
        """Run a query containing a user-supplied search expression, reporting malformed expressions as such."""
        try:
            return connection.execute(sql, params).fetchall()
        except sqlite3.OperationalError as error:
            message = str(error)
            if any(fragment in message for fragment in _USER_QUERY_ERRORS):
                raise InvalidQueryError(f"Invalid search expression: {message}") from error
            raise

    def map_shards[Job, Result](self, function: Callable[[Job], Result], jobs: Iterable[Job]) -> list[Result]:
        """Run ``function`` for every job concurrently. SQLite releases the GIL while querying."""
        return list(self._executor.map(function, jobs))

    # ------------------------------------------------------------------ urns.db

    def shards(self, doctype: str | None = None) -> list[str]:
        """Shard files, optionally only those holding documents of one doctype."""
        with self.connect(URNS_DB) as connection:
            if doctype is None:
                rows = connection.execute("SELECT DISTINCT db_path FROM urns").fetchall()
            else:
                rows = connection.execute("SELECT DISTINCT db_path FROM urns WHERE doctype = ?", (doctype,)).fetchall()
        return sorted(row[0] for row in rows)

    def resolve_urns(self, urns: Sequence[str]) -> list[int]:
        """Dhlabids for the given URNs. If a URN has been indexed several times, the newest version wins."""
        dhlabids = []
        with self.connect(URNS_DB) as connection:
            for batch in batched(dict.fromkeys(urns), _LOOKUP_BATCH_SIZE):
                placeholders = ",".join("?" * len(batch))
                # SQLite takes the bare column ``urn_seq`` from the row that holds max(timestamp).
                sql = f"SELECT urn_seq, max(timestamp) FROM urns WHERE urn IN ({placeholders}) GROUP BY urn"
                dhlabids.extend(row[0] for row in connection.execute(sql, batch))
        return dhlabids

    def locate(self, dhlabids: Sequence[int]) -> list[Document]:
        """Look up which of the given dhlabids exist, and in which shard. Unknown ids are dropped."""
        documents = []
        with self.connect(URNS_DB) as connection:
            for batch in batched(dict.fromkeys(dhlabids), _LOOKUP_BATCH_SIZE):
                placeholders = ",".join("?" * len(batch))
                sql = f"SELECT urn_seq, urn, db_path FROM urns WHERE urn_seq IN ({placeholders})"
                documents.extend(Document(*row) for row in connection.execute(sql, batch))
        return documents

    # ------------------------------------------------------------------ metadata search

    @staticmethod
    def _search_conditions(search: MetadataSearch, table: str) -> tuple[list[str], list[Any], bool] | None:
        """SQL conditions for a search, their parameters and whether any of them is an FTS match.

        Returns ``None`` if the search cannot match anything.
        """
        conditions: list[str] = []
        params: list[Any] = []
        has_match = False

        for column, query in search.match.items():
            if column not in METADATA_COLUMNS:
                raise ValueError(f"Unknown metadata column: {column}")
            conditions.append(f"m.{column} MATCH ?")
            params.append(query)
            has_match = True

        if search.year_from is not None and search.year_to is not None:
            # A closed range is matched against the index, year by year, rather than by scanning the table.
            years = range(max(search.year_from, MIN_YEAR), min(search.year_to, MAX_YEAR) + 1)
            if not years:
                return None
            conditions.append("m.year MATCH ?")
            params.append(" OR ".join(str(year) for year in years))
            has_match = True
        elif search.year_from is not None:
            conditions.append("cast(m.year AS int) >= ?")
            params.append(search.year_from)
        elif search.year_to is not None:
            conditions.append("cast(m.year AS int) <= ?")
            params.append(search.year_to)

        if search.timestamp_from is not None:
            conditions.append("cast(m.timestamp AS int) >= ?")
            params.append(search.timestamp_from)
        if search.timestamp_to is not None:
            conditions.append("cast(m.timestamp AS int) <= ?")
            params.append(search.timestamp_to)

        if search.ddc is not None:
            if "*" in search.ddc:
                conditions.append("m.ddc MATCH ?")
                params.append(search.ddc)
                has_match = True
            else:
                # ddc is a space separated list of classes; match one whole class.
                conditions.append("(m.ddc = ? OR m.ddc LIKE ? OR m.ddc LIKE ? OR m.ddc LIKE ?)")
                params.extend([search.ddc, f"{search.ddc} %", f"% {search.ddc}", f"% {search.ddc} %"])

        if search.fulltext is not None:
            conditions.append("m.doc MATCH ?")
            params.append(search.fulltext)
            has_match = True

        if search.freetext is not None:
            conditions.append(f"{table} MATCH ?")
            params.append(search.freetext)
            has_match = True

        return conditions, params, has_match

    @staticmethod
    def _search_sql(columns: str, table: str, conditions: list[str], search: MetadataSearch, has_match: bool) -> str:
        order = search.order
        sql = f"SELECT {columns} FROM {table} AS m"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        if order == "random":
            # SQLite's random() cannot be seeded, so a seeded search orders by a hash of seed and row instead.
            sql += " ORDER BY random()" if search.seed is None else " ORDER BY seeded_random(m.rowid)"
        elif order == "rank" and has_match:  # bm25 is only defined for full-text matches
            sql += f" ORDER BY bm25({table})"
        return sql + " LIMIT ?"

    def search_metadata(self, search: MetadataSearch) -> list[dict[str, Any]]:
        """Documents whose metadata satisfies the search. ``search.fulltext`` is not supported here."""
        built = self._search_conditions(search, "metadata_core_fts")
        if built is None:
            return []
        conditions, params, has_match = built
        sql = self._search_sql(", ".join(METADATA_COLUMNS), "metadata_core_fts", conditions, search, has_match)
        with self.connect(METADATA_DB) as connection:
            _register_seeded_random(connection, search.seed)
            rows = self._execute_user_query(connection, sql, [*params, search.limit])
        return [dict(zip(METADATA_COLUMNS, row)) for row in rows]

    def search_fulltext_metadata(self, search: MetadataSearch, shards: Sequence[str]) -> list[dict[str, Any]]:
        """Documents whose text and metadata satisfy the search, up to ``search.limit`` from *each* shard."""
        built = self._search_conditions(search, "ft_doc_metadata")
        if built is None:
            return []
        conditions, params, has_match = built
        columns = "urn_seq, " + ", ".join(FULLTEXT_METADATA_COLUMNS[1:])
        sql = self._search_sql(columns, "ft_doc_metadata", conditions, search, has_match)

        def search_shard(shard: str) -> list[tuple]:
            with self.connect(shard) as connection:
                _register_seeded_random(connection, search.seed)
                return self._execute_user_query(connection, sql, [*params, search.limit])

        return [
            dict(zip(FULLTEXT_METADATA_COLUMNS, row)) for rows in self.map_shards(search_shard, shards) for row in rows
        ]

    def match_metadata_urns(self, query: str, limit: int) -> list[str]:
        """URNs of documents whose metadata matches an FTS5 query."""
        sql = "SELECT urn FROM metadata_core_fts WHERE metadata_core_fts MATCH ? LIMIT ?"
        with self.connect(METADATA_DB) as connection:
            return [row[0] for row in self._execute_user_query(connection, sql, (query, limit))]

    # ------------------------------------------------------------------ shard queries

    def concordances(
        self,
        shard: str,
        dhlabids: Sequence[int],
        query: str,
        window: int,
        per_document_limit: int,
        trigram_index: bool = False,
        markers: tuple[str, str, str] = ("", "", ""),
    ) -> list[tuple[int, str]]:
        """Text snippets around the hits for an FTS5 query, as (dhlabid, snippet).

        ``window`` is the snippet length in tokens. ``markers`` is the text inserted before a hit,
        after a hit, and where the snippet is cut off from the surrounding paragraph.
        """
        table = "ft_para_trigram" if trigram_index else "ft_para"
        sql = f"""
            SELECT urn, snippet({table}, 3, ?, ?, ?, ?)
            FROM {table}
            WHERE urn MATCH ? AND para_text MATCH ?
            LIMIT ?
        """
        results: list[tuple[int, str]] = []
        with self.connect(shard) as connection:
            for dhlabid in dhlabids:
                try:
                    rows = self._execute_user_query(
                        connection, sql, (*markers, window, str(dhlabid), query, per_document_limit)
                    )
                except sqlite3.OperationalError as error:
                    if trigram_index and "no such table" in str(error):
                        raise InvalidQueryError("The trigram index is not available for this corpus") from error
                    raise
                results.extend((int(urn), snippet) for urn, snippet in rows)
        return results

    def collocation_counts(
        self,
        shard: str,
        dhlabids: Sequence[int],
        word: str,
        before: int,
        after: int,
        legacy: bool = False,
        per_document_limit: int | None = None,
    ) -> list[tuple[str, int, int]]:
        """Words occurring near ``word``, per document, as (collocate, distance, count).

        ``distance`` is the sum of the distances (in tokens) between the word and the collocate.

        With ``legacy=True`` the numbers are those of the legacy API: the distance is the absolute
        value of the summed *signed* offsets (so collocates before and after the word cancel out),
        and the window is allowed to run into the neighbouring document of the shard.
        """
        distance = "abs(sum(t.rowid - r.rowid))" if legacy else "sum(abs(t.rowid - r.rowid))"
        sql = f"""
            SELECT t.word, {distance}, count(*)
            FROM ft AS t, ft AS r
            WHERE r.word = ?
              AND r.urn = ?
              AND t.rowid >= r.rowid - ?
              AND t.rowid <= r.rowid + ?
              AND t.rowid != r.rowid
              {"" if legacy else "AND +t.urn = r.urn"}
            GROUP BY r.urn, r.word, t.word
            LIMIT ?
        """
        limit = -1 if per_document_limit is None else per_document_limit
        results: list[tuple[str, int, int]] = []
        with self.connect(shard) as connection:
            for dhlabid in dhlabids:
                results.extend(connection.execute(sql, (word, dhlabid, before, after, limit)))
        return results

    def ngram_counts(
        self, shard: str, words: Sequence[str], time_unit: TimeUnit, filters: Sequence[NgramFilter]
    ) -> list[tuple[str, int, int]]:
        """Summed word frequencies per time unit, as (word, year or timestamp, frequency).

        Joins the shard's word counts with ``metadata.db``; that join needs an index starting
        with ``dhlabid`` on ``metadata_core`` to be fast.
        """
        conditions = [f"u.word IN ({','.join('?' * len(words))})"]
        params: list[Any] = list(words)
        for condition in filters:
            if condition.column not in METADATA_COLUMNS:
                raise ValueError(f"Unknown metadata column: {condition.column}")
            conditions.append(f"m.{condition.column} {condition.operator} ?")
            params.append(condition.value)
        sql = f"""
            SELECT u.word, m.{time_unit}, sum(u.freq)
            FROM unigram AS u
            JOIN meta.metadata_core AS m ON u.urn = m.dhlabid
            WHERE {" AND ".join(conditions)}
            GROUP BY u.word, m.{time_unit}
        """
        with self.connect(shard, attach_metadata=True) as connection:
            return connection.execute(sql, params).fetchall()

    # ------------------------------------------------------------------ totals

    def totals(self, limit: int) -> list[tuple[str, int]]:
        """The ``limit`` most frequent words in the whole collection, with their frequencies.

        Reads the precomputed ``grand_total.db`` (see ``scripts/make_grand_total.py``).
        """
        with self.connect(GRAND_TOTAL_DB) as connection:
            sql = "SELECT word, tf FROM grand_total ORDER BY tf DESC LIMIT ?"
            return connection.execute(sql, (limit,)).fetchall()


_MASK64 = 0xFFFFFFFFFFFFFFFF


def _register_seeded_random(connection: sqlite3.Connection, seed: int | None) -> None:
    """Give the connection a ``seeded_random(rowid)`` SQL function: a fixed pseudo-random number per seed and row."""
    if seed is None:
        return

    def seeded_random(rowid: int) -> int:
        # splitmix64: a well mixed 64 bit hash, so that different seeds give unrelated orders.
        z = (rowid + (seed + 1) * 0x9E3779B97F4A7C15) & _MASK64
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return (z ^ (z >> 31)) >> 1  # SQLite integers are signed 64 bit

    connection.create_function("seeded_random", 1, seeded_random, deterministic=True)
