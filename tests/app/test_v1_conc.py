from tests.conftest import ALL_BOOKS, PEER_GYNT, PEER_GYNT_URN


def conc(test_client, **params) -> dict:
    response = test_client.post("/conc", json={"query": "Peer", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_concordances_are_a_column_oriented_table(test_client) -> None:
    table = conc(test_client, dhlabids=[PEER_GYNT], limit=5)
    assert list(table) == ["docid", "urn", "conc"]
    assert list(table["conc"]) == ["0", "1", "2", "3", "4"]
    assert set(table["docid"].values()) == {PEER_GYNT}
    assert set(table["urn"].values()) == {PEER_GYNT_URN}


def test_hits_are_bold_by_default(test_client) -> None:
    table = conc(test_client, dhlabids=[PEER_GYNT], limit=20)
    assert all("<b>" in text and "</b>" in text for text in table["conc"].values())


def test_html_formatting_can_be_turned_off(test_client) -> None:
    table = conc(test_client, dhlabids=[PEER_GYNT], limit=20, html_formatting=False)
    assert not any("<b>" in text for text in table["conc"].values())


def test_corpus_can_be_given_as_urns(test_client) -> None:
    assert set(conc(test_client, urns=[PEER_GYNT_URN], limit=3)["docid"].values()) == {PEER_GYNT}


def test_dhlabids_take_precedence_over_urns(test_client) -> None:
    table = conc(test_client, dhlabids=[100000000], urns=[PEER_GYNT_URN], limit=3)
    assert set(table["docid"].values()) == {100000000}


def test_search_spans_shards_and_skips_unknown_documents(test_client) -> None:
    table = conc(test_client, dhlabids=[*ALL_BOOKS, 999999999], query="og", limit=1000)
    assert len(set(table["docid"].values())) > 3
    assert len(table["conc"]) == 1000


def test_window_is_clamped(test_client) -> None:
    """A window above the maximum of 25 gives the same snippets as a window of 25."""
    params = {"dhlabids": [PEER_GYNT], "limit": 1000}
    too_wide = conc(test_client, **params, window=500)
    widest = conc(test_client, **params, window=25)
    narrow = conc(test_client, **params, window=5)
    assert sorted(too_wide["conc"].values()) == sorted(widest["conc"].values())
    assert sorted(narrow["conc"].values()) != sorted(widest["conc"].values())


def test_no_hits_gives_empty_table(test_client) -> None:
    assert conc(test_client, dhlabids=[PEER_GYNT], query="finnesikke") == {"docid": {}, "urn": {}, "conc": {}}


def test_corpus_is_required(test_client) -> None:
    assert test_client.post("/conc", json={"query": "Peer"}).status_code == 422


def test_malformed_query_is_a_client_error(test_client) -> None:
    response = test_client.post("/conc", json={"dhlabids": [PEER_GYNT], "query": "Peer AND ("})
    assert response.status_code == 400


def test_conccount_counts_tokens_in_concordances(test_client) -> None:
    response = test_client.post("/conccount", json={"dhlabids": [PEER_GYNT], "query": "Peer", "window": 5})
    assert response.status_code == 200
    freq = response.json()["freq"]
    assert freq["Gynt"] > 100
    assert freq["Peer"] >= freq["Gynt"]


def test_conccount_without_hits(test_client) -> None:
    response = test_client.post("/conccount", json={"dhlabids": [PEER_GYNT], "query": "finnesikke"})
    assert response.json() == {"freq": {}}
