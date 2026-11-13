"""Request and response shapes of the legacy API (api.nb.no/dhlab), kept as they are for existing clients."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

type Cell = int | str | None
type TextCell = str | None


class BuildCorpusParams(BaseModel):
    """Metadata filter. Text fields are SQLite FTS5 queries; all given fields must match."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"doctype": "digibok", "title": "Gynt", "limit": 10}]})

    doctype: str | None = Field(None, description="The document type", examples=["digibok"])
    author: str | None = Field(None, description="Author/creator of the document", examples=["Ibsen"])
    from_year: int | None = Field(None, description="Minimum year of publication", examples=[1850])
    to_year: int | None = Field(
        None,
        description="Maximum year of publication. Exclusive when from_year is also given, otherwise inclusive",
        examples=[2021],
    )
    from_timestamp: int | None = Field(
        None, description="Minimum date of publication (YYYYMMDD). Ignored when both years are given"
    )
    to_timestamp: int | None = Field(
        None, description="Maximum date of publication (YYYYMMDD). Ignored when both years are given"
    )
    title: str | None = Field(None, description="Title of the publication")
    ddk: str | None = Field(None, description="Dewey decimal classification", examples=["839.82"])
    subject: str | None = Field(None, description="Subject (keywords) of the publication")
    lang: str | None = Field(None, description="Language(s) of the publication", examples=["nob"])
    publisher: str | None = Field(None, description="Publisher", examples=["Gyldendal"])
    literaryform: str | None = Field(None, description="Literary form (books)", examples=["Skjønnlitteratur"])
    genres: str | None = Field(None, description="Genre of the publication")
    city: str | None = Field(None, description="Place of publication", examples=["Oslo"])
    fulltext: str | None = Field(None, description="Words within the publication", examples=["Norge"])
    freetext: str | None = Field(None, description="Any of the fields", examples=["digibok AND Ibsen"])
    limit: int = Field(10, ge=0, description="Number of items to sample")
    order_by: Literal["random", "rank", "first"] = Field("random", description="Order of the result set")


class MetadataTable(BaseModel):
    """Column oriented metadata table: every column maps a row index (0-indexed) to a value.

    The OCR columns are absent when the corpus was built with a ``fulltext`` filter.
    """

    dhlabid: dict[int, int]
    urn: dict[int, TextCell]
    title: dict[int, TextCell]
    authors: dict[int, TextCell]
    oaiid: dict[int, TextCell]
    sesamid: dict[int, TextCell]
    isbn10: dict[int, TextCell]
    city: dict[int, TextCell]
    timestamp: dict[int, Cell]
    year: dict[int, Cell]
    publisher: dict[int, TextCell]
    langs: dict[int, TextCell]
    subjects: dict[int, TextCell]
    ddc: dict[int, TextCell]
    genres: dict[int, TextCell]
    literaryform: dict[int, TextCell]
    doctype: dict[int, TextCell]
    ocr_creator: dict[int, TextCell] | None = None
    ocr_timestamp: dict[int, Cell] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dhlabid": {"0": 100000001, "1": 100000004},
                    "urn": {"0": "URN:NBN:no-nb_digibok_2017010448142", "1": "URN:NBN:no-nb_digibok_2017020148047"},
                    "title": {"0": "Punch's lomme-Ibsen : fire parodier", "1": "Peer Gynt"},
                    "authors": {"0": "Anstey, F. / Ibsen, Henrik", "1": "Ibsen, Henrik / Hertzberg, Johan"},
                    "oaiid": {"0": "oai:nb.bibsys.no:999407140274702202", "1": "oai:nb.bibsys.no:999412527294702202"},
                    "sesamid": {"0": "af82452c7d772d9d8b43388850f8516a", "1": "0a41cba23f14a3dd7fc0e16b8a6d0ccb"},
                    "isbn10": {"0": "", "1": ""},
                    "city": {"0": "Kristiania", "1": "Oslo"},
                    "timestamp": {"0": 18930101, "1": 19400101},
                    "year": {"0": 1893, "1": 1940},
                    "publisher": {"0": "Norli", "1": "Gyldendal"},
                    "langs": {"0": "nob", "1": "nob"},
                    "subjects": {"0": "parodi", "1": ""},
                    "ddc": {"0": "", "1": ""},
                    "genres": {"0": "", "1": ""},
                    "literaryform": {"0": "Uklassifisert", "1": "Uklassifisert"},
                    "doctype": {"0": "digibok", "1": "digibok"},
                    "ocr_creator": {"0": "nb", "1": "nb"},
                    "ocr_timestamp": {"0": 20060101, "1": 20060101},
                }
            ]
        }
    )


class _CorpusParams(BaseModel):
    dhlabids: list[int] | None = Field(None, description="A list of dhlabids", examples=[[100000000, 100000001]])
    urns: list[str] | None = Field(
        None,
        description="A list of URNs. Ignored if dhlabids is given",
        examples=[["URN:NBN:no-nb_digibok_2017020148047"]],
    )

    @model_validator(mode="after")
    def has_corpus(self):
        if self.dhlabids is None and self.urns is None:
            raise ValueError("Either dhlabids or urns is required")
        return self


class ConcParams(_CorpusParams):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"urns": ["URN:NBN:no-nb_digibok_2017020148047"], "query": "Peer", "window": 20, "limit": 10}]
        }
    )
    query: str = Field(description="A SQLite fulltext (FTS5) query", examples=["Norge"])
    window: int = Field(20, description="Size of the text snippet, in tokens. Clamped to 1-25", examples=[20])
    limit: int = Field(1000, ge=0, description="Max. number of concordances, in total and (at most 1000) per document")
    trigram_index: bool = Field(False, description="Use the experimental, case sensitive, character trigram index")
    html_formatting: bool = Field(
        True, description='Pad the snippets with "..." and wrap the hits in html boldface tags (<b></b>)'
    )


class ConcordanceTable(BaseModel):
    """Column oriented table of concordances, in random order."""

    docid: dict[int, int]
    urn: dict[int, str]
    conc: dict[int, str]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "docid": {"0": 100000004},
                    "urn": {"0": "URN:NBN:no-nb_digibok_2017020148047"},
                    "conc": {"0": "... du lyver ! <b>Peer</b> Gynt . Nei , jeg gjør ei ..."},
                }
            ]
        }
    )


class ConcCountParams(_CorpusParams):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"urns": ["URN:NBN:no-nb_digibok_2017020148047"], "query": "Peer", "window": 10, "limit": 100}]
        }
    )
    query: str = Field(description="A SQLite fulltext (FTS5) query", examples=["Norge"])
    window: int = Field(10, description="Size of the text snippet, in tokens. At most 100", examples=[10])
    limit: int = Field(1000, ge=0, description="Max. number of concordances per document (at most 1000)")
    trigram_index: bool = Field(False, description="Use the experimental, case sensitive, character trigram index")


class ConcCountTable(BaseModel):
    freq: dict[str, int] = Field(description="Number of occurrences of every token in the concordances")


class CollocationParams(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"word": "Peer", "metadata_query": "Gynt", "before": 5, "after": 5}]}
    )
    word: str = Field(description="The word to find collocates of", examples=["kaffe"])
    before: int = Field(5, description="Number of tokens before the word to include")
    after: int = Field(5, description="Number of tokens after the word to include")
    metadata_query: str = Field("norge", description="FTS5 metadata query selecting the corpus")
    samplesize: int = Field(50000, ge=0, description="Number of documents to sample from the corpus (at most 20000)")


class CollocationUrnParams(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"word": "Peer", "urn": ["URN:NBN:no-nb_digibok_2017020148047"], "before": 5, "after": 5}]
        }
    )
    word: str = Field(description="The word to find collocates of", examples=["kaffe"])
    before: int = Field(5, description="Number of tokens before the word to include")
    after: int = Field(5, description="Number of tokens after the word to include")
    samplesize: int = Field(5000, ge=0, description="Number of documents to sample from the corpus (at most 50000)")
    urn: list[str] | None = Field(None, description="The corpus as a list of URNs")
    dhlabid: list[int] | None = Field(None, description="The corpus as a list of dhlabids. Ignored if urn is given")


def _as_list(value: object) -> object:
    return [value] if isinstance(value, str) else value


type Words = Annotated[list[str], BeforeValidator(_as_list)]
type Period = tuple[int, int]


class NgramParams(BaseModel):
    """Filters are SQL LIKE patterns (use ``%`` as wildcard), except city which must match exactly."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"word": ["og", "i"], "period": [1830, 1950]}]})

    word: Words = Field(description="A list of words (at most 1000 are used)", examples=[["sushi", "pizza"]])
    title: str | None = Field(None, description="Title")
    publisher: str | None = Field(None, description="Publisher")
    lang: str | None = Field(None, description="Language")
    city: str | None = Field(None, description="Publication city")
    period: Period | None = Field(
        None, description="Period of publication (from year, to year). Default 1950-1990", examples=[[1990, 2020]]
    )
    ddk: str | None = Field(None, description="Dewey decimal classification")
    topic: str | None = Field(None, description="Subject word")


class NgramNewspaperParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"word": ["og", "i"], "period": [1850, 1890]}]})
    word: Words = Field(description="A list of words (at most 1000 are used)", examples=[["sushi", "pizza"]])
    title: str | None = Field(None, description="Exact title of the newspaper")
    period: Period | None = Field(
        None,
        description=(
            "Period of publication. Both ends are given as YYYY (counts per year), "
            "or YYYYMM or YYYYMMDD (counts per date). Default 19500101-19901231"
        ),
        examples=[[1990, 2020]],
    )
