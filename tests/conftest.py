import time
import typing as tp
from http import HTTPMethod
from types import MethodType

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.openapi.utils import get_openapi
from starlette.requests import Request
from starlette.testclient import TestClient

from fast_cache_middleware import CacheConfig, CacheDropConfig, FastCacheMiddleware


async def get_storage_depends(request: Request) -> tp.Any:
    return request.app.state.storage


async def create_user(user_id: int, storage: dict = Depends(get_storage_depends)):
    user_name = str(time.time)
    storage[user_id] = user_name
    return {"user_id": user_id, "name": user_name, "timestamp": time.time()}


async def get_user(user_id: int, storage: dict = Depends(get_storage_depends)):
    try:
        user_name = storage[user_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "name": user_name, "timestamp": time.time()}


async def delete_user(user_id: int, storage: dict = Depends(get_storage_depends)):
    user_name = storage.pop(user_id)
    return {"user_id": user_id, "name": user_name, "timestamp": time.time()}


async def get_first_user(storage: dict = Depends(get_storage_depends)):
    return await get_user(1, storage=storage)


async def get_second_user(storage: dict = Depends(get_storage_depends)):
    return await get_user(2, storage=storage)


async def hidden_route():
    return {"hidden": True}


@pytest.fixture
def app() -> FastAPI:
    _storage = {
        1: "first",
        2: "second",
    }

    app = FastAPI()
    app.add_middleware(FastCacheMiddleware)
    app.state.storage = _storage

    app.router.add_api_route(
        "/users/first",
        get_first_user,
        dependencies=[CacheDropConfig(["/users/second"])],
        methods={HTTPMethod.GET.value},
    )
    app.router.add_api_route(
        "/users/second",
        get_second_user,
        dependencies=[CacheConfig(max_age=5)],
        methods={HTTPMethod.GET.value},
    )
    app.router.add_api_route(
        "/users/{user_id}",
        get_user,
        dependencies=[CacheConfig(max_age=10)],
        methods={HTTPMethod.GET.value},
    )
    app.router.add_api_route(
        "/users/{user_id}",
        create_user,
        dependencies=[CacheDropConfig(paths=["/users/"])],
        methods={HTTPMethod.POST.value},
    )
    app.router.add_api_route(
        "/users/{user_id}",
        delete_user,
        dependencies=[CacheDropConfig(methods=[get_user])],
        methods={HTTPMethod.DELETE.value},
    )
    app.router.add_api_route(
        "/no-docs",
        hidden_route,
        include_in_schema=False,
        dependencies=[CacheConfig(max_age=42)],
        methods={HTTPMethod.GET.value},
    )

    def custom_openapi() -> dict[str, tp.Any]:
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title="Custom title",
            version="2.5.0",
            summary="This is a very custom OpenAPI schema",
            description="Here's a longer description of the custom **OpenAPI** schema",
            routes=app.routes,
        )
        openapi_schema["info"]["x-logo"] = {
            "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore

    second_app = FastAPI()
    second_app.add_middleware(FastCacheMiddleware)
    second_app.state.storage = _storage

    second_app.router.add_api_route(
        "/users/first",
        get_first_user,
        dependencies=[CacheDropConfig(["/subapp/users/second"])],
        methods={HTTPMethod.GET.value},
    )
    second_app.router.add_api_route(
        "/users/second",
        get_second_user,
        dependencies=[CacheConfig(max_age=5)],
        methods={HTTPMethod.GET.value},
    )
    app.mount("/subapp", app=second_app)

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Создает тестовый клиент."""
    return TestClient(app)
