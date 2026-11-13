import sqlite3
from collections import Counter

import pytest

from tests.conftest import ALL_BOOKS, PEER_GYNT, PEER_GYNT_URN
from tests.expected_corpus_urns import DIGAVIS_URNS, DIGIBOK_URNS, DIGITIDSSKRIFT_URNS


def post(test_client, path, **body):
    response = test_client.post(f"/v2/{path}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- corpus


@pytest.mark.parametrize(
    "doctype, expected_urns",
    [("digibok", DIGIBOK_URNS), ("digavis", DIGAVIS_URNS), ("digitidsskrift", DIGITIDSSKRIFT_URNS)],
)
def test_corpus_by_doctype(test_client, doctype, expected_urns) -> None:
    documents = post(test_client, "corpus", doctype=doctype, limit=100)
    assert {document["urn"] for document in documents} == expected_urns


def test_corpus_documents_are_records_with_nulls_for_missing_values(test_client) -> None:
    (document,) = post(test_client, "corpus", title="Gynt")
    assert document["dhlabid"] == PEER_GYNT
    assert document["urn"] == PEER_GYNT_URN
    assert document["year"] == 1940
    assert document["subjects"] is None


def test_corpus_year_range_is_inclusive(test_client) -> None:
    documents = post(test_client, "corpus", doctype="digibok", year_from=1893, year_to=1894)
    assert {document["year"] for document in documents} == {1893, 1894}


def test_corpus_date_range(test_client) -> None:
    documents = post(test_client, "corpus", date_from="1870-03-01", date_to="1870-03-31")
    assert [document["dhlabid"] for document in documents] == [200000002]


def test_corpus_order_first_is_deterministic(test_client) -> None:
    documents = post(test_client, "corpus", doctype="digibok", order_by="first", limit=3)
    assert [document["dhlabid"] for document in documents] == ALL_BOOKS[:3]


def test_corpus_fulltext(test_client) -> None:
    documents = post(test_client, "corpus", fulltext="Peer", title="Gynt")
    assert [document["dhlabid"] for document in documents] == [PEER_GYNT]
    assert documents[0]["ocr_creator"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"doctype": "not_a_doctype"},
        {"limit": 0},
        {"year_from": 1900, "year_to": 1800},
        {"date_from": "18700301"},
        {"author": ""},
        {"unknown_field": 1},
    ],
)
def test_corpus_rejects_invalid_requests(test_client, body) -> None:
    assert test_client.post("/v2/corpus", json=body).status_code == 422


def test_corpus_malformed_query_is_a_client_error(test_client) -> None:
    response = test_client.post("/v2/corpus", json={"freetext": "AND AND"})
    assert response.status_code == 400
    assert "Invalid search expression" in response.json()["detail"]


# ---------------------------------------------------------------- concordance


def test_concordance_records(test_client) -> None:
    concordances = post(test_client, "concordance", dhlabids=[PEER_GYNT], query="Peer", limit=5)
    assert len(concordances) == 5
    assert all(set(c) == {"dhlabid", "urn", "text"} for c in concordances)
    assert all(c["urn"] == PEER_GYNT_URN and "<b>" not in c["text"] for c in concordances)


def test_concordance_with_highlight(test_client) -> None:
    concordances = post(test_client, "concordance", dhlabids=[PEER_GYNT], query="Peer", highlight=True)
    assert all(c["dhlabid"] == PEER_GYNT and "<b>" in c["text"] for c in concordances)


@pytest.mark.parametrize(
    "body",
    [
        {"query": "Peer"},
        {"query": "Peer", "urns": [PEER_GYNT_URN]},
        {"query": "Peer", "dhlabids": [PEER_GYNT_URN]},
        {"query": "Peer", "dhlabids": []},
        {"query": "Peer", "dhlabids": [PEER_GYNT], "window": 26},
        {"query": "Peer", "dhlabids": [PEER_GYNT], "limit": 0},
        {"query": " ", "dhlabids": [PEER_GYNT]},
        {"query": "Peer", "dhlabids": list(range(30_001))},
    ],
)
def test_concordance_rejects_invalid_requests(test_client, body) -> None:
    assert test_client.post("/v2/concordance", json=body).status_code == 422


def test_concordance_malformed_query_is_a_client_error(test_client) -> None:
    response = test_client.post("/v2/concordance", json={"dhlabids": [PEER_GYNT], "query": '"Peer'})
    assert response.status_code == 400


def test_concordance_without_trigram_index_is_a_client_error(test_client) -> None:
    """The test database is built without the trigram index."""
    body = {"dhlabids": [PEER_GYNT], "query": "eer", "trigram_index": True}
    assert test_client.post("/v2/concordance", json=body).status_code == 400


# ---------------------------------------------------------------- collocations


def test_collocations_are_sorted_by_count(test_client) -> None:
    collocates = post(test_client, "collocations", dhlabids=[PEER_GYNT], word="Peer", before=0, after=1)
    assert collocates[0]["word"] == "Gynt"
    assert collocates[0]["mean_distance"] == 1
    counts = [collocate["count"] for collocate in collocates]
    assert counts == sorted(counts, reverse=True)


def test_collocation_distance_is_within_window(test_client) -> None:
    collocates = post(test_client, "collocations", dhlabids=[PEER_GYNT], word="Peer", before=3, after=3)
    assert all(1 <= collocate["mean_distance"] <= 3 for collocate in collocates)


def test_collocation_window_stays_within_the_document(test_client, database_dir) -> None:
    """Counts equal a straightforward count over the document's own tokens, also for its very first token."""
    dhlabid, before, after = 100000002, 3, 2  # not the first document of its shard
    with sqlite3.connect(database_dir / "alto_100000001_100000004.db") as connection:
        rows = connection.execute("SELECT word FROM ft WHERE urn = ? ORDER BY rowid", (dhlabid,))
        tokens = [row[0] for row in rows]
    word = tokens[0]
    expected = Counter()
    for position, token in enumerate(tokens):
        if token == word:
            expected.update(tokens[max(position - before, 0) : position] + tokens[position + 1 : position + after + 1])

    collocates = post(test_client, "collocations", dhlabids=[dhlabid], word=word, before=before, after=after)
    assert {collocate["word"]: collocate["count"] for collocate in collocates} == expected


@pytest.mark.parametrize(
    "body", [{"word": "Peer"}, {"word": "", "dhlabids": [1]}, {"word": "a", "dhlabids": [1], "before": -1}]
)
def test_collocations_reject_invalid_requests(test_client, body) -> None:
    assert test_client.post("/v2/collocations", json=body).status_code == 422


# ---------------------------------------------------------------- totals and ngram


def test_totals(test_client) -> None:
    totals = test_client.get("/v2/totals", params={"limit": 2}).json()
    assert totals == [{"word": ".", "frequency": 26521}, {"word": ",", "frequency": 20396}]


def test_totals_limit_must_be_positive(test_client) -> None:
    assert test_client.get("/v2/totals", params={"limit": 0}).status_code == 422


def test_ngram_gives_one_series_per_word(test_client) -> None:
    series = post(test_client, "ngram", words=["Peer", "Nora", "finnesikke"], year_from=1880, year_to=1950)
    assert series == [
        {"word": "Peer", "frequencies": [{"year": 1890, "frequency": 4}, {"year": 1940, "frequency": 395}]},
        {"word": "Nora", "frequencies": [{"year": 1890, "frequency": 686}, {"year": 1893, "frequency": 30}]},
        {"word": "finnesikke", "frequencies": []},
    ]


def test_ngram_doctype_and_filter(test_client) -> None:
    series = post(test_client, "ngram", words=["og"], doctype="digavis", year_from=1800, year_to=1950, title="vg%")
    assert series == [{"word": "og", "frequencies": [{"year": 1870, "frequency": 304}]}]


@pytest.mark.parametrize(
    "body", [{}, {"words": []}, {"words": ["og"], "doctype": "digimanus"}, {"words": ["og"], "year_from": 2000}]
)
def test_ngram_rejects_invalid_requests(test_client, body) -> None:
    assert test_client.post("/v2/ngram", json=body).status_code == 422


# ---------------------------------------------------------------- seeding


def results_for_seeds(test_client, path, seeds, **body) -> list[str]:
    return [str(post(test_client, path, **body, seed=seed)) for seed in seeds]


@pytest.mark.parametrize(
    "path, body",
    [
        ("corpus", {"limit": 5}),
        ("corpus", {"fulltext": "og", "limit": 5}),
        ("concordance", {"dhlabids": ALL_BOOKS, "query": "og", "limit": 20}),
        ("concordance", {"dhlabids": [PEER_GYNT], "query": "Peer", "limit": 1000}),
    ],
)
def test_same_seed_gives_same_result_and_other_seeds_differ(test_client, path, body) -> None:
    assert len(set(results_for_seeds(test_client, path, [7, 7, 7], **body))) == 1
    assert len(set(results_for_seeds(test_client, path, range(10), **body))) > 1


def test_without_seed_results_vary(test_client) -> None:
    results = {str(post(test_client, "corpus", limit=5)) for _ in range(10)}
    assert len(results) > 1


def test_seed_must_not_be_negative(test_client) -> None:
    assert test_client.post("/v2/corpus", json={"seed": -1}).status_code == 422
