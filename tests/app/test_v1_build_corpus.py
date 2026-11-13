import pytest

from tests.expected_corpus_urns import DIGAVIS_URNS, DIGIBOK_URNS, DIGITIDSSKRIFT_URNS

OCR_COLUMNS = {"ocr_creator", "ocr_timestamp"}


def build(test_client, **params) -> dict:
    response = test_client.post("/build_corpus", json={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


def titles(table: dict) -> set[str]:
    return set(table["title"].values())


@pytest.mark.parametrize(
    "doctype, expected_urns",
    [("digibok", DIGIBOK_URNS), ("digavis", DIGAVIS_URNS), ("digitidsskrift", DIGITIDSSKRIFT_URNS)],
)
def test_doctype_filter_returns_expected_urns(test_client, doctype, expected_urns) -> None:
    assert set(build(test_client, doctype=doctype)["urn"].values()) == expected_urns


def test_table_is_column_oriented_with_string_row_indexes(test_client) -> None:
    table = build(test_client, doctype="digavis", order_by="first")
    assert OCR_COLUMNS < set(table)
    assert all(list(column) == ["0", "1", "2"] for column in table.values())
    assert table["dhlabid"] == {"0": 200000000, "1": 200000001, "2": 200000002}


def test_no_filter_gives_default_sample_of_ten(test_client) -> None:
    response = test_client.post("/build_corpus", json={})
    assert response.status_code == 200
    assert len(response.json()["urn"]) == 10


def test_limit(test_client) -> None:
    assert len(build(test_client, doctype="digibok", limit=4)["urn"]) == 4


def test_filters_are_combined(test_client) -> None:
    assert titles(build(test_client, doctype="digibok", publisher="Gyldendal", city="Oslo")) == {"Peer Gynt"}


def test_to_year_is_exclusive_when_from_year_is_given(test_client) -> None:
    """Legacy quirk: 1893 is included, 1894 is not."""
    table = build(test_client, doctype="digibok", from_year=1893, to_year=1894)
    assert set(table["year"].values()) == {1893}


def test_single_year_bounds_are_inclusive(test_client) -> None:
    assert set(build(test_client, doctype="digibok", to_year=1887)["year"].values()) == {1872, 1887}
    assert set(build(test_client, doctype="digibok", from_year=1940)["year"].values()) == {1940}


def test_timestamp_bounds(test_client) -> None:
    table = build(test_client, from_timestamp=18700301, to_timestamp=18700331)
    assert titles(table) == {"VG (1868-1923) "}


def test_ddk_matches_a_whole_class(test_client) -> None:
    assert len(build(test_client, ddk="058.82")["urn"]) == 2
    assert len(build(test_client, ddk="058.8")["urn"]) == 0


def test_punctuation_is_stripped_from_plain_queries(test_client) -> None:
    assert titles(build(test_client, title="Gynt!?")) == {"Peer Gynt"}


def test_fts_syntax_is_kept_when_quoted(test_client) -> None:
    assert titles(build(test_client, title='"Peer Gynt" OR "Sankt Hans"')) == {
        "Peer Gynt",
        "Sankt Hans Fest : Fortælling",
    }


def test_freetext_searches_all_fields(test_client) -> None:
    assert titles(build(test_client, freetext="Gyldendal AND 1940")) == {"Peer Gynt"}


def test_fulltext_searches_document_text_across_shards(test_client) -> None:
    table = build(test_client, fulltext="Peer")
    assert "Peer Gynt" in titles(table)
    assert not OCR_COLUMNS & set(table)
    assert {dhlabid // 100000000 for dhlabid in table["dhlabid"].values()} == {1}


def test_fulltext_with_metadata_filter_and_rank(test_client) -> None:
    table = build(test_client, fulltext="Peer", doctype="digibok", title="Gynt", order_by="rank")
    assert titles(table) == {"Peer Gynt"}


def test_malformed_query_is_a_client_error(test_client) -> None:
    response = test_client.post("/build_corpus", json={"title": '"unbalanced'})
    assert response.status_code == 400


def test_wrong_type_is_a_validation_error(test_client) -> None:
    assert test_client.post("/build_corpus", json={"from_year": "long ago"}).status_code == 422
