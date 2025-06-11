import typing as tp
from starlette.responses import Response
from starlette.requests import Request
import json
import copy
from datetime import datetime

# Определяем типы для метаданных и хранимого ответа
Metadata: tp.TypeAlias = tp.Dict[str, tp.Any]
StoredResponse: tp.TypeAlias = tp.Tuple[Response, Request, Metadata]


class BaseSerializer:
    def dumps(
        self, response: Response, request: Request, metadata: Metadata
    ) -> tp.Union[str, bytes]:
        raise NotImplementedError()

    def loads(
        self, data: tp.Union[str, bytes]
    ) -> tp.Tuple[Response, Request, Metadata]:
        raise NotImplementedError()

    @property
    def is_binary(self) -> bool:
        raise NotImplementedError()


class JSONSerializer(BaseSerializer):
    def dumps(self, response: Response, request: Request, metadata: Metadata) -> str:
        serialized = {
            "response": {
                "status_code": response.status_code,
                "headers": [[k.decode(), v.decode()] for k, v in response.headers.raw],
                "content": response.body.decode("utf-8", errors="ignore")
                if response.body
                else None,
            },
            "request": {
                "method": request.method,
                "url": str(request.url),
                "headers": [[k.decode(), v.decode()] for k, v in request.headers.raw],
            },
            "metadata": metadata,
        }
        return json.dumps(serialized)

    def loads(self, data: tp.Union[str, bytes]) -> StoredResponse:
        if isinstance(data, bytes):
            data = data.decode()

        parsed = json.loads(data)

        # Восстанавливаем Response
        response_data = parsed["response"]
        response = Response(
            content=response_data["content"].encode("utf-8")
            if response_data["content"]
            else b"",
            status_code=response_data["status_code"],
            headers=dict(response_data["headers"]),
        )

        # Восстанавливаем Request - создаем mock объект для совместимости
        request_data = parsed["request"]

        # Создаем минимальный scope для Request
        from urllib.parse import urlparse

        parsed_url = urlparse(request_data["url"])
        scope = {
            "type": "http",
            "method": request_data["method"],
            "path": parsed_url.path,
            "query_string": parsed_url.query.encode() if parsed_url.query else b"",
            "headers": [[k.encode(), v.encode()] for k, v in request_data["headers"]],
        }

        # Создаем пустую receive функцию
        async def receive():
            return {"type": "http.request", "body": b""}

        request = Request(scope, receive)

        return response, request, parsed["metadata"]

    @property
    def is_binary(self) -> bool:
        return False
