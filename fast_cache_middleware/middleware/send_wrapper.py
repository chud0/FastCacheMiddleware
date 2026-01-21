import typing as tp

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from fast_cache_middleware.storages import BaseStorage
from fast_cache_middleware.controller import Controller

from .base import BaseSendWrapper


class CacheSendWrapper(BaseSendWrapper):
    def __init__(
        self,
        controller: Controller,
        storage: BaseStorage,
        request: Request,
        cache_key: str,
        ttl: int,
        app: ASGIApp,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        super().__init__(app, scope, receive, send)

        self.controller = controller
        self.storage = storage
        self.request = request
        self.cache_key = cache_key
        self.ttl = ttl

    async def on_response_start(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        message.get("headers", []).append(("X-Cache-Status".encode(), "MISS".encode()))
        return await super().on_response_start(message)

    async def on_response_ready(self, response: Response) -> None:
        await self.controller.cache_response(
            cache_key=self.cache_key,
            request=self.request,
            response=response,
            storage=self.storage,
            ttl=self.ttl,
        )
