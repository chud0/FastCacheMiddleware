import logging
import typing as tp

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class BaseMiddleware:
    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        self.app = app

        self.executors_map = {
            "lifespan": self.on_lifespan,
            "http": self.on_http,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        try:
            is_request_processed = await self.executors_map[scope_type](
                scope, receive, send
            )
        except KeyError:
            logger.debug("Not supported scope type: %s", scope_type)
            is_request_processed = False

        if not is_request_processed:
            await self.app(scope, receive, send)

    async def on_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> bool | None:
        pass

    async def on_http(self, scope: Scope, receive: Receive, send: Send) -> bool | None:
        pass


class BaseSendWrapper:
    def __init__(self, app: ASGIApp, scope: Scope, receive: Receive, send: Send):
        self.app = app
        self.scope = scope
        self.receive = receive
        self.send = send

        self._response_status: int = 200
        self._response_headers: dict[str, str] = dict()
        self._response_body: bytes = b""

        self.executors_map = {
            "http.response.start": self.on_response_start,
            "http.response.body": self.on_response_body,
        }

    async def __call__(self) -> None:
        return await self.app(self.scope, self.receive, self._message_processor)

    async def _message_processor(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        try:
            executor = self.executors_map[message["type"]]
        except KeyError:
            logger.error("Not found executor for %s message type", message["type"])
        else:
            await executor(message)

        await self.send(message)

    async def on_response_start(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        self._response_status = message["status"]
        self._response_headers = {
            k.decode(): v.decode() for k, v in message.get("headers", [])
        }

    async def on_response_body(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        self._response_body += message.get("body", b"")

        # this is the last chunk
        if not message.get("more_body", False):
            response = Response(
                content=self._response_body,
                status_code=self._response_status,
                headers=self._response_headers,
            )
            await self.on_response_ready(response)

    async def on_response_ready(self, response: Response) -> None:
        pass
