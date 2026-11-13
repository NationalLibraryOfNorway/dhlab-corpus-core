import pytest

from dhlab_core_api.config import Config

V1_POST = ["build_corpus", "conc", "conccount", "urncolldist", "urncolldist_urn"]
V1_POST += ["ngram_book", "ngram_periodicals", "ngram_newspapers"]
V2_POST = ["corpus", "concordance", "collocations", "ngram"]


def test_root_points_to_docs(test_client) -> None:
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


@pytest.mark.parametrize("path", [f"/{name}" for name in V1_POST] + [f"/v2/{name}" for name in V2_POST])
def test_post_endpoint_is_mounted(test_client, path) -> None:
    """Sending a list where an object is expected is a validation error (422), not a missing route (404)."""
    assert test_client.post(path, json=[]).status_code == 422


def test_openapi_schema_is_generated(test_client) -> None:
    paths = test_client.get("/openapi.json").json()["paths"]
    assert "/totals/{top_words}" in paths
    assert "/v2/totals" in paths


def test_config_is_read_from_env_file(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("DATABASE_DIR=/some/where\nMAX_WORKERS=3\nROOT_PATH=/dhlab\n")
    monkeypatch.chdir(tmp_path)
    config = Config()
    assert (str(config.database_dir), config.max_workers, config.root_path) == ("/some/where", 3, "/dhlab")
