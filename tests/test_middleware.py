"""Тесты для оптимизированного FastCacheMiddleware."""

import time
import typing as tp
from http import HTTPMethod

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

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
        dependencies=[CacheDropConfig(paths=["/users/"])],
        methods={HTTPMethod.DELETE.value},
    )
    app.router.add_api_route(
        "/no-docs",
        hidden_route,
        include_in_schema=False,
        dependencies=[CacheConfig(max_age=42)],
        methods={HTTPMethod.GET.value},
    )

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


def test_caching_works(client: TestClient) -> None:
    """Тестирует кеширование"""
    # Первый запрос
    response1 = client.get("/users/1")
    assert response1.status_code == 200
    data1 = response1.json()

    # Второй запрос - должен быть кеширован
    response2 = client.get("/users/1")
    assert response2.status_code == 200
    data2 = response2.json()

    # Данные должны быть одинаковыми
    assert data1 == data2


def test_cache_invalidation(client: TestClient) -> None:
    """Тестирует инвалидацию кеша."""
    response1 = client.get("/users/1")
    assert response1.status_code == 200

    response_invalidate = client.delete("/users/1")
    assert response_invalidate.status_code == 200

    # Следующий GET запрос должен выполнить новый запрос (не кешированный)
    response2 = client.get("/users/1")
    assert response2.status_code == 404


def test_different_users_different_cache(client: TestClient) -> None:
    """Тестирует, что разные пользователи имеют разные кеши."""
    # Запрос для пользователя 1
    response1 = client.get("/users/1")
    assert response1.status_code == 200
    data1 = response1.json()

    # Запрос для пользователя 2
    response2 = client.get("/users/2")
    assert response2.status_code == 200
    data2 = response2.json()

    # Данные должны быть разными
    assert data1["user_id"] != data2["user_id"]
    assert data1["name"] != data2["name"]


def test_stay_order_endpoints(client: TestClient) -> None:
    response1 = client.get("/users/second").json()

    # it must invalidate
    client.get("/users/first")

    response2 = client.get("/users/second").json()

    assert response1["timestamp"] != response2["timestamp"]


def test_middleware_isolated(client: TestClient) -> None:
    """
    test to ensure that middleware operates in isolation:
     - first request can cache the drop config
     - third request incorrectly invalidates the cache
     - response2 will contain cached response
    """
    client.get("/users/first")

    response1 = client.get("/subapp/users/second").json()
    client.get("/subapp/users/first")
    response2 = client.get("/subapp/users/second").json()

    assert response1["timestamp"] != response2["timestamp"]


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


def test_openapi_patch_keyerror_handled_gracefully(
    app: FastAPI, client: TestClient
) -> None:
    path = "/no-docs"

    client.get(path)
    schema = app.openapi()
    assert path not in schema["paths"]
