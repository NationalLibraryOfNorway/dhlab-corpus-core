"""Translation between v2 datatypes and the version independent service layer."""

from collections import Counter
from collections.abc import Sequence
from typing import Any

from dhlab_core_api.repository import MetadataSearch, NgramFilter
from dhlab_core_api.service import Collocations
from dhlab_core_api.v1.legacy import fts_escape
from dhlab_core_api.v2.datatypes import Collocate, CorpusQuery, Document, NgramQuery, NgramSeries, YearFrequency

# CorpusQuery field -> metadata column, for the fields that are FTS5 queries
_MATCH_COLUMNS = {
    "doctype": "doctype",
    "author": "authors",
    "title": "title",
    "publisher": "publisher",
    "city": "city",
    "language": "langs",
    "subject": "subjects",
    "genre": "genres",
    "literary_form": "literaryform",
}

# NgramQuery field -> metadata column
_NGRAM_COLUMNS = {
    "title": "title",
    "publisher": "publisher",
    "city": "city",
    "language": "langs",
    "subject": "subjects",
    "ddc": "ddc",
}


def metadata_search(query: CorpusQuery) -> MetadataSearch:
    # Punctuation is not searchable (and breaks FTS5 syntax), so it is stripped from plain queries.
    match = fts_escape({key: str(value) for key in _MATCH_COLUMNS if (value := getattr(query, key)) is not None})
    return MetadataSearch(
        match={_MATCH_COLUMNS[key]: value for key, value in match.items()},
        ddc=query.ddc,
        year_from=query.year_from,
        year_to=query.year_to,
        timestamp_from=None if query.date_from is None else int(query.date_from.strftime("%Y%m%d")),
        timestamp_to=None if query.date_to is None else int(query.date_to.strftime("%Y%m%d")),
        freetext=query.freetext,
        fulltext=query.fulltext,
        order=query.order_by,
        limit=query.limit,
        seed=query.seed,
    )


def documents(rows: Sequence[dict[str, Any]]) -> list[Document]:
    """Metadata rows as documents; the database's empty strings become nulls."""
    return [Document(**{column: None if value == "" else value for column, value in row.items()}) for row in rows]


def collocates(collocations: Collocations) -> list[Collocate]:
    """Collocates, most frequent first."""
    return [
        Collocate(word=word, count=count, mean_distance=collocations.distances[word] / count)
        for word, count in sorted(collocations.counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def ngram_filters(query: NgramQuery) -> list[NgramFilter]:
    filters = [NgramFilter("year", ">=", query.year_from), NgramFilter("year", "<=", query.year_to)]
    for field, column in _NGRAM_COLUMNS.items():
        if (value := getattr(query, field)) is not None:
            filters.append(NgramFilter(column, "LIKE", value))
    return filters


def ngram_series(words: Sequence[str], counts: Counter[tuple[str, int]]) -> list[NgramSeries]:
    """One series per requested word, in the order requested, each sorted by year."""
    by_word: dict[str, list[YearFrequency]] = {word: [] for word in words}
    for (word, year), frequency in sorted(counts.items()):
        by_word[word].append(YearFrequency(year=year, frequency=frequency))
    return [NgramSeries(word=word, frequencies=frequencies) for word, frequencies in by_word.items()]
