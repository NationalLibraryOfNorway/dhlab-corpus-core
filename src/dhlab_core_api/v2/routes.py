from typing import Annotated

from fastapi import APIRouter, Query

from dhlab_core_api.service import CorpusService
from dhlab_core_api.v2 import mapping
from dhlab_core_api.v2.datatypes import (
    Collocate,
    CollocationQuery,
    Concordance,
    ConcordanceQuery,
    CorpusQuery,
    Document,
    NgramQuery,
    NgramSeries,
    WordFrequency,
)


def get_v2_router(service: CorpusService) -> APIRouter:
    v2 = APIRouter(prefix="/v2", tags=["v2"], responses={400: {"description": "Malformed search expression"}})

    @v2.post("/corpus")
    def build_corpus(query: CorpusQuery) -> list[Document]:
        """Build a corpus: metadata for documents that satisfy the filter"""
        return mapping.documents(service.build_corpus(mapping.metadata_search(query)))

    @v2.post("/concordance")
    def concordance(query: ConcordanceQuery) -> list[Concordance]:
        """Concordances (keyword in context) for a text query in a corpus, in random order"""
        concordances = service.concordance(
            query.dhlabids,
            query=query.query,
            window=query.window,
            limit=query.limit,
            trigram_index=query.trigram_index,
            html_formatting=query.highlight,
            seed=query.seed,
        )
        return [Concordance(dhlabid=c.dhlabid, urn=c.urn, text=c.text) for c in concordances]

    @v2.post("/collocations")
    def collocations(query: CollocationQuery) -> list[Collocate]:
        """Words occurring near a word in a corpus, most frequent first.

        The window never crosses a document boundary.
        """
        result = service.collocations(query.dhlabids, query.word, query.before, query.after)
        return mapping.collocates(result)

    @v2.get("/totals")
    def totals(limit: Annotated[int, Query(ge=1, le=1_000_000)] = 50_000) -> list[WordFrequency]:
        """The most frequent words in the whole collection, for use as a reference frequency list"""
        return [WordFrequency(word=word, frequency=frequency) for word, frequency in service.totals(limit)]

    @v2.post("/ngram")
    def ngram(query: NgramQuery) -> list[NgramSeries]:
        """Frequency per year of each word, in documents of one type that satisfy the filter"""
        words = list(dict.fromkeys(query.words))
        counts = service.ngram(query.doctype, words, "year", mapping.ngram_filters(query))
        return mapping.ngram_series(words, counts)

    return v2
