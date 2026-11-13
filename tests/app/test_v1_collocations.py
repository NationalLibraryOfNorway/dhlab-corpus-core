import json

from tests.conftest import PEER_GYNT, PEER_GYNT_URN


def collocations(test_client, path="/urncolldist_urn", **params) -> dict:
    response = test_client.post(path, json={"word": "Peer", **params})
    assert response.status_code == 200, response.text
    # The legacy API returns a JSON string containing JSON.
    assert isinstance(response.json(), str)
    return json.loads(response.json())


def test_collocation_table(test_client) -> None:
    table = collocations(test_client, dhlabid=[PEER_GYNT], before=0, after=1)
    assert list(table) == ["counts", "dist", "bdist"]
    assert table["counts"]["Gynt"] > 100
    # Every "Gynt" is one token after "Peer", so the summed distance equals the count.
    assert table["dist"]["Gynt"] == table["counts"]["Gynt"]
    assert table["bdist"]["Gynt"] == (table["dist"]["Gynt"] + 2) / (table["counts"]["Gynt"] + 2)


def test_table_is_sorted_by_bdist(test_client) -> None:
    bdist = [value for value in collocations(test_client, dhlabid=[PEER_GYNT])["bdist"].values() if value is not None]
    assert bdist == sorted(bdist)


def test_corpus_can_be_given_as_urns(test_client) -> None:
    by_urn = collocations(test_client, urn=[PEER_GYNT_URN], before=0, after=1)
    by_id = collocations(test_client, dhlabid=[PEER_GYNT], before=0, after=1)
    assert by_urn["counts"] == by_id["counts"]


def test_no_corpus_gives_empty_object(test_client) -> None:
    assert test_client.post("/urncolldist_urn", json={"word": "Peer"}).json() == {}


def test_corpus_from_metadata_query(test_client) -> None:
    table = collocations(test_client, path="/urncolldist", metadata_query="Gynt", before=0, after=1)
    assert table["counts"]["Gynt"] > 100


def test_metadata_query_without_matches_gives_empty_table(test_client) -> None:
    table = collocations(test_client, path="/urncolldist", metadata_query="finnesikke")
    assert table == {"counts": {}, "dist": {}, "bdist": {}}
