from fastapi import FastAPI
from starlette.testclient import TestClient


def test_set_cache_age_to_openapi_schema(app: FastAPI, client: TestClient) -> None:
    path = "/users/second"
    method = "get"

    client.get(path)
    schema = app.openapi()

    assert path in schema["paths"]
    assert method in schema["paths"][path]

    operation = schema["paths"][path][method]

    assert "x-cache-age" in operation
    assert operation["x-cache-age"] == 5


def test_x_logo_field_exists_after_set_cache_age(
    app: FastAPI, client: TestClient
) -> None:
    path = "/users/second"
    method = "get"

    client.get(path)
    schema = app.openapi()
    operation = schema["paths"][path][method]

    assert "x-logo" in schema["info"]
    assert "x-cache-age" in operation


def test_openapi_patch_keyerror_handled_gracefully(
    app: FastAPI, client: TestClient
) -> None:
    path = "/no-docs"

    client.get(path)
    schema = app.openapi()
    assert path not in schema["paths"]
