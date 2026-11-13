"""The legacy API's quirks: how its parameters are interpreted and how its (pandas-shaped) results look.

Kept apart from the service so the peculiarities of v1 do not leak into shared code.
"""

import json
import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

from dhlab_core_api.repository import MetadataSearch, NgramFilter, TimeUnit
from dhlab_core_api.service import Collocations, bayesian_distance
from dhlab_core_api.v1.datatypes import BuildCorpusParams, NgramNewspaperParams, NgramParams

MAX_NGRAM_WORDS = 1000

# build_corpus parameter -> metadata column, for the fields that are FTS5 queries
_MATCH_COLUMNS = {
    "doctype": "doctype",
    "author": "authors",
    "title": "title",
    "subject": "subjects",
    "lang": "langs",
    "publisher": "publisher",
    "literaryform": "literaryform",
    "genres": "genres",
    "city": "city",
}
_UNESCAPED = {"freetext", "limit", "ddk", "order_by"}


def fts_escape(params: dict[str, Any]) -> dict[str, Any]:
    """Basic cleaning of FTS searches: drops empty values and strips punctuation from simple queries.

    Queries containing double quotes or parentheses are assumed to be deliberate FTS5 syntax and are left alone.
    """
    escaped = {}
    for key, value in params.items():
        if key in _UNESCAPED:
            escaped[key] = value
        elif not value:
            continue
        elif isinstance(value, str) and '"' not in value and "(" not in value:
            cleaned = re.sub(r"[^\w\*\+\^\s]+", "", value)
            if cleaned:
                escaped[key] = cleaned
        else:
            escaped[key] = value
    return escaped


def metadata_search(params: BuildCorpusParams) -> MetadataSearch:
    values = fts_escape(params.model_dump(exclude_none=True))

    from_year, to_year = values.get("from_year"), values.get("to_year")
    from_timestamp, to_timestamp = values.get("from_timestamp"), values.get("to_timestamp")
    if from_year is not None and to_year is not None:
        # Legacy quirk: with both years given, to_year is exclusive and the timestamps are ignored.
        to_year = min(to_year, 2030) - 1
        from_timestamp = to_timestamp = None

    return MetadataSearch(
        match={column: values[key] for key, column in _MATCH_COLUMNS.items() if key in values},
        ddc=values.get("ddk") or None,
        year_from=from_year,
        year_to=to_year,
        timestamp_from=from_timestamp,
        timestamp_to=to_timestamp,
        freetext=values.get("freetext"),
        fulltext=values.get("fulltext"),
        order=params.order_by,
        limit=params.limit,
    )


def column_table(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> dict[str, dict[int, Any]]:
    """Rows as pandas' default ``DataFrame.to_json()`` layout: {column: {row index: value}}."""
    return {column: {index: row[column] for index, row in enumerate(rows)} for column in columns}


def collocation_json(collocations: Collocations, before: int, after: int) -> str:
    """Collocations as the JSON *string* the legacy API returns: columns counts, dist and bdist, sorted by bdist.

    Legacy quirk: a collocate whose summed distance is zero has ``null`` for dist and bdist.
    """
    rows = []
    for word, count in collocations.counts.items():
        distance = collocations.distances[word] or None
        bdist = None if distance is None else bayesian_distance(distance, count, before, after)
        rows.append((word, count, distance, bdist))
    rows.sort(key=lambda row: (row[3] is None, row[3] or 0))
    return json.dumps(
        {
            "counts": {word: count for word, count, _, _ in rows},
            "dist": {word: distance for word, _, distance, _ in rows},
            "bdist": {word: bdist for word, _, _, bdist in rows},
        }
    )


def ngram_filters(params: NgramParams, exact_language: bool) -> list[NgramFilter]:
    """Metadata conditions for book and periodical n-grams (counted per year)."""
    year_from, year_to = params.period or (1950, 1990)
    filters = [NgramFilter("year", ">=", year_from), NgramFilter("year", "<=", year_to)]
    if params.lang is not None:
        filters.append(NgramFilter("langs", "=" if exact_language else "LIKE", params.lang))
    if params.city is not None:
        filters.append(NgramFilter("city", "=", params.city))
    if params.title is not None:
        filters.append(NgramFilter("title", "LIKE", params.title))
    if params.publisher is not None:
        filters.append(NgramFilter("publisher", "LIKE", params.publisher))
    if params.ddk is not None:
        filters.append(NgramFilter("ddc", "LIKE", params.ddk))
    if params.topic is not None:
        filters.append(NgramFilter("subjects", "LIKE", params.topic))
    return filters


def newspaper_ngram_filters(params: NgramNewspaperParams) -> tuple[TimeUnit, list[NgramFilter]]:
    """Metadata conditions for newspaper n-grams. The precision of the period decides the time unit."""
    start, end = (str(bound) for bound in params.period or (19500101, 19901231))
    time_unit: TimeUnit = "timestamp"
    if len(start) != len(end) or len(start) not in (4, 6, 8):
        start, end = "20000101", "20000201"
    elif len(start) == 4:
        time_unit = "year"
    elif len(start) == 6:
        # Legacy quirk: a month is replaced by its first day, so the last month only counts that one day.
        start, end = start + "01", end + "01"

    filters = [NgramFilter(time_unit, ">=", int(start)), NgramFilter(time_unit, "<=", int(end))]
    if params.title is not None:
        filters.append(NgramFilter("title", "=", params.title))
    return time_unit, filters


def ngram_table(counts: Counter[tuple[str, int]]) -> dict[str, int]:
    """N-gram counts keyed by "<word> <year or date>"."""
    return {f"{word} {time}": frequency for (word, time), frequency in counts.items()}
