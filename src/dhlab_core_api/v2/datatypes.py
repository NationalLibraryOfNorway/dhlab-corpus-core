"""Request and response shapes of v2: row oriented, strictly validated, explicit about bounds."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_CORPUS_SIZE = 30_000

type FtsQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type Word = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class Doctype(StrEnum):
    digibok = "digibok"
    digavis = "digavis"
    digitidsskrift = "digitidsskrift"
    digistorting = "digistorting"
    digimanus = "digimanus"
    kudos = "kudos"


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpusQuery(_Request):
    """Metadata filter for building a corpus. All given fields must match.

    Text fields are matched word by word; `*` at the end of a word matches any ending, and
    FTS5 syntax (`"exact phrase"`, `(a OR b)`, `NOT`) may be used when the value contains quotes or parentheses.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{"doctype": "digibok", "title": "Gynt", "limit": 10}]})

    doctype: Doctype | None = Field(None, description="Document type")
    author: FtsQuery | None = Field(None, examples=["Ibsen"])
    title: FtsQuery | None = Field(None, examples=["Peer Gynt"])
    publisher: FtsQuery | None = Field(None, examples=["Gyldendal"])
    city: FtsQuery | None = Field(None, description="Place of publication", examples=["Oslo"])
    language: FtsQuery | None = Field(None, description="Language code(s) of the document", examples=["nob"])
    subject: FtsQuery | None = Field(None, description="Subject keywords")
    genre: FtsQuery | None = None
    literary_form: FtsQuery | None = Field(None, examples=["Skjønnlitteratur"])
    ddc: FtsQuery | None = Field(
        None, description="Dewey decimal class. Exact, or a prefix when it ends with `*`", examples=["839.82"]
    )
    year_from: int | None = Field(None, description="First year of publication (inclusive)", examples=[1850])
    year_to: int | None = Field(None, description="Last year of publication (inclusive)", examples=[1900])
    date_from: date | None = Field(None, description="First date of publication (inclusive)")
    date_to: date | None = Field(None, description="Last date of publication (inclusive)")
    freetext: FtsQuery | None = Field(None, description="FTS5 query against all metadata fields")
    fulltext: FtsQuery | None = Field(None, description="FTS5 query against the text of the documents")
    limit: int = Field(10, ge=1, le=100_000, description="Maximum number of documents")
    order_by: Literal["random", "rank", "first"] = Field(
        "random", description="`random` gives a random sample, `rank` the best matches, `first` the lowest dhlabids"
    )
    seed: int | None = Field(
        None,
        ge=0,
        description="Makes the random sample reproducible: the same request with the same seed gives the same result",
    )

    @model_validator(mode="after")
    def ranges_are_ordered(self):
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("year_from must not be after year_to")
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class Document(BaseModel):
    """Metadata for one document. Missing values are null."""

    dhlabid: int
    urn: str
    doctype: str
    title: str | None
    authors: str | None
    year: int | None
    timestamp: int | None = Field(description="Date of publication as YYYYMMDD (books have YYYY0101)")
    city: str | None
    publisher: str | None
    langs: str | None
    subjects: str | None
    ddc: str | None
    genres: str | None
    literaryform: str | None
    oaiid: str | None
    sesamid: str | None
    isbn10: str | None
    ocr_creator: str | None = None
    ocr_timestamp: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dhlabid": 100000004,
                    "urn": "URN:NBN:no-nb_digibok_2017020148047",
                    "doctype": "digibok",
                    "title": "Peer Gynt",
                    "authors": "Ibsen, Henrik / Hertzberg, Johan",
                    "year": 1940,
                    "timestamp": 19400101,
                    "city": "Oslo",
                    "publisher": "Gyldendal",
                    "langs": "nob",
                    "subjects": None,
                    "ddc": None,
                    "genres": None,
                    "literaryform": "Uklassifisert",
                    "oaiid": "oai:nb.bibsys.no:999412527294702202",
                    "sesamid": "0a41cba23f14a3dd7fc0e16b8a6d0ccb",
                    "isbn10": None,
                    "ocr_creator": "nb",
                    "ocr_timestamp": 20060101,
                }
            ]
        }
    )


class _CorpusRequest(_Request):
    """The corpus is given as a list of dhlabids, the identifier of a document in the DH-lab collection."""

    dhlabids: list[int] = Field(min_length=1, max_length=MAX_CORPUS_SIZE, examples=[[100000004]])


class ConcordanceQuery(_CorpusRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [{"dhlabids": [100000004], "query": "Peer", "limit": 10}]})
    query: FtsQuery = Field(description="FTS5 query against the text", examples=["Norge"])
    window: int = Field(20, ge=1, le=25, description="Size of each text snippet, in tokens")
    limit: int = Field(
        100, ge=1, le=10_000, description="Maximum number of concordances (at most 1000 are taken from one document)"
    )
    highlight: bool = Field(False, description="Wrap the hits in `<b></b>` and mark truncated snippets with `...`")
    trigram_index: bool = Field(
        False, description="Search the case sensitive character trigram index, which finds parts of words"
    )
    seed: int | None = Field(
        None,
        ge=0,
        description="Makes the random selection and order reproducible: the same request with the same seed gives the same result",
    )


class Concordance(BaseModel):
    dhlabid: int
    urn: str
    text: str = Field(examples=["du lyver ! Peer Gynt . Nei , jeg gjør ei"])


class CollocationQuery(_CorpusRequest):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"dhlabids": [100000004], "word": "Peer", "before": 5, "after": 5}]}
    )
    word: Word = Field(description="The word to find collocates of (case sensitive)", examples=["kaffe"])
    before: int = Field(5, ge=0, le=50, description="Number of tokens before the word to include")
    after: int = Field(5, ge=0, le=50, description="Number of tokens after the word to include")


class Collocate(BaseModel):
    word: str
    count: int = Field(description="Number of times the collocate occurs within the window")
    mean_distance: float = Field(description="Average distance from the word, in tokens (1 = adjacent)")


class WordFrequency(BaseModel):
    word: str
    frequency: int


class NgramQuery(_Request):
    """Text filters are SQL LIKE patterns: case insensitive, `%` matches anything."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"doctype": "digibok", "words": ["og", "i"], "year_from": 1850, "year_to": 1950}]
        }
    )

    doctype: Literal[Doctype.digibok, Doctype.digavis, Doctype.digitidsskrift] = Doctype.digibok
    words: list[Word] = Field(min_length=1, max_length=100, examples=[["sushi", "pizza"]])
    year_from: int = Field(1950, description="First year (inclusive)")
    year_to: int = Field(1990, description="Last year (inclusive)")
    title: str | None = Field(None, examples=["aftenposten"])
    publisher: str | None = None
    city: str | None = None
    language: str | None = Field(None, examples=["nob"])
    subject: str | None = None
    ddc: str | None = Field(None, examples=["839%"])

    @model_validator(mode="after")
    def years_are_ordered(self):
        if self.year_from > self.year_to:
            raise ValueError("year_from must not be after year_to")
        return self


class YearFrequency(BaseModel):
    year: int
    frequency: int


class NgramSeries(BaseModel):
    """Frequency of one word per year. Years in which the word does not occur are left out."""

    word: str
    frequencies: list[YearFrequency]
