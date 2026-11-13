"""Unit tests for the legacy API's parameter and result conventions."""

import json
from collections import Counter

from dhlab_core_api.service import Collocations
from dhlab_core_api.v1 import legacy
from dhlab_core_api.v1.datatypes import BuildCorpusParams, NgramNewspaperParams


def test_fts_escape_strips_punctuation_and_drops_empty_values() -> None:
    escaped = legacy.fts_escape({"author": "Ibsen, Henrik", "title": "", "city": "?!", "from_year": 1900})
    assert escaped == {"author": "Ibsen Henrik", "from_year": 1900}


def test_fts_escape_keeps_wildcards_and_deliberate_fts_syntax() -> None:
    params = {"title": "dikt*", "author": '"Ibsen, Henrik"', "subject": "(a OR b)", "freetext": "x: y", "ddk": "839.82"}
    assert legacy.fts_escape(params) == params


def test_metadata_search_with_both_years_makes_to_year_exclusive_and_drops_timestamps() -> None:
    search = legacy.metadata_search(BuildCorpusParams(from_year=1900, to_year=1910, from_timestamp=19050101))
    assert (search.year_from, search.year_to, search.timestamp_from) == (1900, 1909, None)


def test_metadata_search_maps_parameters_to_columns() -> None:
    search = legacy.metadata_search(BuildCorpusParams(author="Ibsen", lang="nob", subject="dikt", order_by="rank"))
    assert search.match == {"authors": "Ibsen", "langs": "nob", "subjects": "dikt"}
    assert (search.order, search.limit) == ("rank", 10)


def test_column_table() -> None:
    assert legacy.column_table([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], ["a", "b"]) == {
        "a": {0: 1, 1: 2},
        "b": {0: "x", 1: "y"},
    }


def test_collocation_json_has_null_distance_when_offsets_cancel_out() -> None:
    collocations = Collocations(counts=Counter(near=2, far=1, balanced=2), distances=Counter(near=2, far=5, balanced=0))
    table = json.loads(legacy.collocation_json(collocations, before=5, after=5))
    assert list(table["bdist"]) == ["near", "far", "balanced"]
    assert table["dist"] == {"near": 2, "far": 5, "balanced": None}
    assert table["bdist"] == {"near": 0.5, "far": 5 / 3, "balanced": None}


def test_newspaper_period_with_mismatched_precision_falls_back_to_january_2000() -> None:
    time_unit, filters = legacy.newspaper_ngram_filters(NgramNewspaperParams(word=["a"], period=(1990, 199912)))
    assert time_unit == "timestamp"
    assert [f.value for f in filters] == [20000101, 20000201]
