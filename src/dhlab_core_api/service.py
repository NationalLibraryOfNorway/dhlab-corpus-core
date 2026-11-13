"""Business logic, independent of both the HTTP layer and the database layout.

The service decides *what* to compute (sampling, limits, aggregation across shards); the
repository knows *how* to get it out of the database; the versioned routers decide how
requests and responses look.
"""

import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dhlab_core_api.repository import CorpusRepository, Document, MetadataSearch, NgramFilter, TimeUnit

MAX_CONCORDANCES_PER_DOCUMENT = 1000
MAX_URNS_PER_REQUEST = 500_000

# Snippet decorations: (before hit, after hit, where the snippet is cut off).
HTML_MARKERS = ("<b>", "</b>", "... ")
NO_MARKERS = ("", "", "")


@dataclass(frozen=True)
class Concordance:
    dhlabid: int
    urn: str
    text: str


@dataclass(frozen=True)
class Collocations:
    """Collocates of a word: how often each occurs in the window, and its summed distance to the word."""

    counts: Counter[str]
    distances: Counter[str]


class CorpusService:
    def __init__(self, repository: CorpusRepository) -> None:
        self.repository = repository

    # ------------------------------------------------------------------ corpus

    def build_corpus(self, search: MetadataSearch) -> list[dict[str, Any]]:
        """Metadata for at most ``search.limit`` documents that satisfy the search."""
        if search.fulltext is None:
            return self.repository.search_metadata(search)

        doctype = search.match.get("doctype")
        # Only look in the shards of the requested doctype, if it names one.
        shards = (doctype and self.repository.shards(doctype)) or self.repository.shards()
        documents = self.repository.search_fulltext_metadata(search, shards)
        # Every shard returns up to `limit` documents.
        if len(documents) > search.limit:
            documents = _random(search.seed).sample(documents, search.limit)
        return documents

    def resolve_urns(self, urns: Sequence[str]) -> list[int]:
        return self.repository.resolve_urns(urns[:MAX_URNS_PER_REQUEST])

    def dhlabids_from_metadata_query(self, query: str, max_documents: int) -> list[int]:
        """A random sample of the documents whose metadata matches an FTS5 query."""
        urns = self.repository.match_metadata_urns(query, limit=2_000_000)
        return self.resolve_urns(_sample(urns, max_documents))

    def _locate(self, dhlabids: Sequence[int], max_documents: int | None) -> dict[str, list[Document]]:
        """Group the existing documents among ``dhlabids`` by shard, sampling if there are too many."""
        if max_documents is not None:
            dhlabids = _sample(dhlabids, max_documents)
        by_shard: dict[str, list[Document]] = defaultdict(list)
        for document in self.repository.locate(dhlabids):
            by_shard[document.shard].append(document)
        return by_shard

    # ------------------------------------------------------------------ concordance

    def concordance(
        self,
        dhlabids: Sequence[int],
        query: str,
        window: int,
        limit: int,
        trigram_index: bool = False,
        html_formatting: bool = False,
        max_documents: int | None = None,
        seed: int | None = None,
    ) -> list[Concordance]:
        """Up to ``limit`` randomly chosen and ordered snippets (of ``window`` tokens) around hits for ``query``."""
        by_shard = self._locate(dhlabids, max_documents)
        urns = {document.dhlabid: document.urn for documents in by_shard.values() for document in documents}
        snippets = self._snippets(by_shard, query, window, limit, trigram_index, html_formatting)
        concordances = [Concordance(dhlabid, urns[dhlabid], text) for dhlabid, text in snippets]
        if len(concordances) > limit:
            return _random(seed).sample(concordances, limit)
        _random(seed).shuffle(concordances)
        return concordances

    def concordance_token_counts(
        self,
        dhlabids: Sequence[int],
        query: str,
        window: int,
        limit: int,
        trigram_index: bool = False,
        max_documents: int | None = None,
    ) -> Counter[str]:
        """Token frequencies in the concordance snippets for ``query`` (``limit`` snippets per document)."""
        by_shard = self._locate(dhlabids, max_documents)
        counts: Counter[str] = Counter()
        for _, text in self._snippets(by_shard, query, window, limit, trigram_index, html_formatting=False):
            counts.update(token for token in text.split(" ") if token)
        return counts

    def _snippets(
        self,
        by_shard: dict[str, list[Document]],
        query: str,
        window: int,
        limit: int,
        trigram_index: bool,
        html_formatting: bool,
    ) -> list[tuple[int, str]]:
        markers = HTML_MARKERS if html_formatting else NO_MARKERS
        per_document_limit = min(limit, MAX_CONCORDANCES_PER_DOCUMENT)

        def shard_snippets(job: tuple[str, list[Document]]) -> list[tuple[int, str]]:
            shard, documents = job
            return self.repository.concordances(
                shard, [d.dhlabid for d in documents], query, window, per_document_limit, trigram_index, markers
            )

        return [
            snippet for snippets in self.repository.map_shards(shard_snippets, by_shard.items()) for snippet in snippets
        ]

    # ------------------------------------------------------------------ collocations

    def collocations(
        self,
        dhlabids: Sequence[int],
        word: str,
        before: int,
        after: int,
        legacy: bool = False,
        per_document_limit: int | None = None,
        max_documents: int | None = None,
    ) -> Collocations:
        """Count the words found up to ``before`` tokens before and ``after`` tokens after each occurrence of ``word``.

        ``legacy`` selects the legacy API's way of measuring distance, see the repository.
        """
        by_shard = self._locate(dhlabids, max_documents)

        def shard_counts(job: tuple[str, list[Document]]) -> list[tuple[str, int, int]]:
            shard, documents = job
            return self.repository.collocation_counts(
                shard, [d.dhlabid for d in documents], word, before, after, legacy, per_document_limit
            )

        counts: Counter[str] = Counter()
        distances: Counter[str] = Counter()
        for rows in self.repository.map_shards(shard_counts, by_shard.items()):
            for collocate, distance, count in rows:
                counts[collocate] += count
                distances[collocate] += distance
        return Collocations(counts=counts, distances=distances)

    # ------------------------------------------------------------------ totals and n-grams

    def totals(self, limit: int) -> list[tuple[str, int]]:
        """The ``limit`` most frequent words of the collection."""
        return self.repository.totals(limit)

    def ngram(
        self, doctype: str, words: Sequence[str], time_unit: TimeUnit, filters: Sequence[NgramFilter]
    ) -> Counter[tuple[str, int]]:
        """Frequency of each word per year (or per date) in documents of one doctype matching the filters."""
        words = list(dict.fromkeys(words))
        if not words:
            return Counter()

        def shard_counts(shard: str) -> list[tuple[str, int, int]]:
            return self.repository.ngram_counts(shard, words, time_unit, filters)

        counts: Counter[tuple[str, int]] = Counter()
        for rows in self.repository.map_shards(shard_counts, self.repository.shards(doctype)):
            for word, time, frequency in rows:
                counts[word, time] += frequency
        return counts


def bayesian_distance(distance: float, count: int, before: int, after: int) -> float:
    """Average distance to a collocate, smoothed towards the window size so rare collocates do not dominate."""
    return (distance + abs(after - before) * 2) / (count + 2)


def _random(seed: int | None) -> random.Random:
    """A reproducible random number generator for a seed, or a fresh, unpredictable one without."""
    return random.Random(seed)


def _sample[T](items: Sequence[T], size: int) -> Sequence[T]:
    return random.sample(items, size) if len(items) > size else items
