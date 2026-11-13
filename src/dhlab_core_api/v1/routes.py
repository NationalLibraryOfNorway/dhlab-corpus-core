from typing import Annotated

from fastapi import APIRouter, Path

from dhlab_core_api.repository import FULLTEXT_METADATA_COLUMNS, METADATA_COLUMNS
from dhlab_core_api.service import CorpusService
from dhlab_core_api.v1 import legacy
from dhlab_core_api.v1.datatypes import (
    BuildCorpusParams,
    CollocationParams,
    CollocationUrnParams,
    ConcCountParams,
    ConcCountTable,
    ConcordanceTable,
    ConcParams,
    MetadataTable,
    NgramNewspaperParams,
    NgramParams,
    _CorpusParams,
)

MAX_CORPUS_SIZE = 30000


def get_v1_router(service: CorpusService) -> APIRouter:
    v1 = APIRouter(tags=["v1"])

    def corpus_ids(params: _CorpusParams) -> list[int]:
        return params.dhlabids if params.dhlabids is not None else service.resolve_urns(params.urns)

    @v1.post("/build_corpus", response_model_exclude_unset=True)
    def build_corpus(params: BuildCorpusParams) -> MetadataTable:
        """Build corpus from metadata"""
        search = legacy.metadata_search(params)
        documents = service.build_corpus(search)
        columns = METADATA_COLUMNS if search.fulltext is None else FULLTEXT_METADATA_COLUMNS
        return MetadataTable(**legacy.column_table(documents, columns))

    @v1.post("/conc")
    def conc(params: ConcParams) -> ConcordanceTable:
        """Return concordances (keyword in context) for a corpus query.

        If the corpus has more than 30 000 documents, a random sample of them is searched.
        """
        concordances = service.concordance(
            corpus_ids(params),
            query=params.query,
            window=min(max(params.window, 1), 25),
            limit=params.limit,
            trigram_index=params.trigram_index,
            html_formatting=params.html_formatting,
            max_documents=MAX_CORPUS_SIZE,
        )
        return ConcordanceTable(
            docid={index: c.dhlabid for index, c in enumerate(concordances)},
            urn={index: c.urn for index, c in enumerate(concordances)},
            conc={index: c.text for index, c in enumerate(concordances)},
        )

    @v1.post("/conccount")
    def conccount(params: ConcCountParams) -> ConcCountTable:
        """Return token counts from concordances for a corpus query (used for collocation analysis)"""
        counts = service.concordance_token_counts(
            corpus_ids(params),
            query=params.query,
            window=min(params.window, 100),
            limit=params.limit,
            trigram_index=params.trigram_index,
            max_documents=MAX_CORPUS_SIZE,
        )
        return ConcCountTable(freq=dict(sorted(counts.items())))

    @v1.post("/urncolldist")
    def urncolldist(params: CollocationParams) -> str:
        """Collocations of a word in a corpus selected by a metadata query.

        The response is a JSON *string* which itself contains JSON: a table with the columns
        `counts`, `dist` and `bdist`, keyed by collocate.
        """
        dhlabids = service.dhlabids_from_metadata_query(params.metadata_query, min(20000, params.samplesize))
        collocations = service.collocations(
            dhlabids, params.word, params.before, params.after, legacy=True, per_document_limit=1000
        )
        return legacy.collocation_json(collocations, params.before, params.after)

    @v1.post("/urncolldist_urn")
    def urncolldist_urn(params: CollocationUrnParams) -> str | dict:
        """Collocations of a word in a corpus given as a list of URNs or dhlabids.

        The response is a JSON *string* which itself contains JSON: a table with the columns
        `counts`, `dist` and `bdist`, keyed by collocate. Without a corpus, it is an empty object.
        """
        if params.urn is not None:
            dhlabids = service.resolve_urns(params.urn)
        elif params.dhlabid is not None:
            dhlabids = params.dhlabid
        else:
            return {}
        collocations = service.collocations(
            dhlabids,
            params.word,
            params.before,
            params.after,
            legacy=True,
            per_document_limit=1000,
            max_documents=min(50000, params.samplesize),
        )
        return legacy.collocation_json(collocations, params.before, params.after)

    @v1.get("/totals/{top_words}")
    def totals(top_words: Annotated[int, Path(ge=0, examples=[10])]) -> list[tuple[str, int]]:
        """Reference frequency list: the n most frequent words of the collection as [word, frequency] pairs"""
        return service.totals(top_words)

    @v1.post("/ngram_book")
    def ngram_book(params: NgramParams) -> dict[str, int]:
        """Aggregated word frequencies per year for books, keyed by "word year" """
        filters = legacy.ngram_filters(params, exact_language=False)
        counts = service.ngram("digibok", params.word[: legacy.MAX_NGRAM_WORDS], "year", filters)
        return legacy.ngram_table(counts)

    @v1.post("/ngram_periodicals")
    def ngram_periodicals(params: NgramParams) -> dict[str, int]:
        """Aggregated word frequencies per year for periodicals, keyed by "word year" """
        filters = legacy.ngram_filters(params, exact_language=True)
        counts = service.ngram("digitidsskrift", params.word[: legacy.MAX_NGRAM_WORDS], "year", filters)
        return legacy.ngram_table(counts)

    @v1.post("/ngram_newspapers")
    def ngram_newspapers(params: NgramNewspaperParams) -> dict[str, int]:
        """Aggregated word frequencies per year or date for newspapers, keyed by "word year" or "word date" """
        time_unit, filters = legacy.newspaper_ngram_filters(params)
        counts = service.ngram("digavis", params.word[: legacy.MAX_NGRAM_WORDS], time_unit, filters)
        return legacy.ngram_table(counts)

    return v1
