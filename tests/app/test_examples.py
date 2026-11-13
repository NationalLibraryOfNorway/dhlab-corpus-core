"""The request examples shown in the interactive docs must return something from the test database."""

import json

import pytest

from dhlab_core_api.app import make_app
from dhlab_core_api.config import Config

SCHEMA = make_app(Config()).openapi()
POST_PATHS = sorted(path for path, operations in SCHEMA["paths"].items() if "post" in operations)


def is_empty(result) -> bool:
    """An empty list, or a table (object) without rows, or a series without frequencies."""
    if isinstance(result, str):  # legacy collocations: JSON inside a JSON string
        result = json.loads(result)
    if isinstance(result, dict):
        return all(value in ({}, []) for value in result.values())
    return all(is_empty(item) for item in result if isinstance(item, dict)) if result else True


@pytest.mark.parametrize("path", POST_PATHS)
def test_documented_example_returns_data(test_client, path) -> None:
    body_schema = SCHEMA["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
    model = SCHEMA["components"]["schemas"][body_schema["$ref"].rsplit("/", 1)[-1]]
    (example,) = model["examples"]

    response = test_client.post(path, json=example)

    assert response.status_code == 200, response.text
    assert not is_empty(response.json()), response.text
