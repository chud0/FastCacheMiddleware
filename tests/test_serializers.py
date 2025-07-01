import json

import pytest
from starlette import status
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.serializers import JSONSerializer, Metadata


@pytest.fixture
def test_request() -> Request:
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [(b"host", b"test.com"), (b"user-agent", b"pytest")],
        }
    )


@pytest.fixture
def test_response() -> Response:
    return Response(
        content="hello world", status_code=status.HTTP_200_OK, headers={"X-Test": "yes"}
    )


@pytest.fixture
def test_metadata() -> Metadata:
    return {"meta": "value", "ttl": 123}


def test_dumps_output_is_valid_json(test_request, test_response, test_metadata):
    serializer = JSONSerializer()

    result = serializer.dumps(test_response, test_request, test_metadata)
    parsed = json.loads(result)

    assert "response" in parsed
    assert "request" in parsed
    assert "metadata" in parsed

    assert parsed["response"]["status_code"] == status.HTTP_200_OK
    assert parsed["response"]["content"] == "hello world"
    assert parsed["response"]["headers"]["x-test"] == "yes"

    assert parsed["request"]["method"] == "GET"
    assert parsed["request"]["headers"]["host"] == "test.com"
    assert parsed["metadata"]["ttl"] == 123


def test_loads_reconstructs_response_request(
    test_request, test_response, test_metadata
):
    serializer = JSONSerializer()

    json_data = serializer.dumps(test_response, test_request, test_metadata)
    response, request, metadata = serializer.loads(json_data)

    assert isinstance(response, Response)
    assert response.body == b"hello world"
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["x-test"] == "yes"

    assert isinstance(request, Request)
    assert request.method == "GET"
    assert request.url.path == "/test"
    assert request.headers["host"] == "test.com"
    assert request.headers["user-agent"] == "pytest"

    assert metadata == test_metadata


def test_loads_accepts_bytes_input(test_request, test_response, test_metadata):
    serializer = JSONSerializer()

    json_data_str = serializer.dumps(test_response, test_request, test_metadata)
    json_data_bytes = json_data_str.encode("utf-8")

    response, request, metadata = serializer.loads(json_data_bytes)

    assert isinstance(response, Response)
    assert isinstance(request, Request)
    assert metadata == test_metadata


def test_dumps_handles_empty_body(test_request, test_metadata):
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    serializer = JSONSerializer()

    json_str = serializer.dumps(response, test_request, test_metadata)
    parsed = json.loads(json_str)

    assert parsed["response"]["status_code"] == status.HTTP_204_NO_CONTENT
    assert parsed["response"]["content"] is None


def test_is_binary_property():
    serializer = JSONSerializer()
    assert not serializer.is_binary
