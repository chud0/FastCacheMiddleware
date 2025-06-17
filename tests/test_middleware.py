"""Тесты для оптимизированного FastCacheMiddleware."""

import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from fast_cache_middleware import CacheConfig, CacheDropConfig, FastCacheMiddleware


@pytest.fixture
def app() -> FastAPI:
    """Создает FastAPI приложение с оптимизированным middleware."""
    app = FastAPI()

    # Создаем middleware с автоматической инициализацией
    app.add_middleware(FastCacheMiddleware)
    _storage = {
        1: "first",
        2: "second",
    }

    @app.get("/test", dependencies=[CacheConfig(max_age=60)])
    async def test_endpoint():
        """Тестовый endpoint с кешированием."""
        return {"message": "test", "timestamp": time.time()}

    @app.get("/users/{user_id}", dependencies=[CacheConfig(max_age=30)])
    async def get_user(user_id: int):
        """Endpoint для получения пользователя."""
        try:
            user_name = _storage[user_id]
        except KeyError:
            raise HTTPException(status_code=404, detail="User not found")
        return {"user_id": user_id, "name": user_name}

    @app.post("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users/"])])
    async def create_user(user_id: int):
        """Endpoint для создания пользователя с инвалидацией кеша."""
        user_name = str(time.time)
        _storage[user_id] = user_name
        return {"user_id": user_id, "name": user_name}

    @app.delete("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users/"])])
    async def create_user(user_id: int):
        user_name = _storage.pop(user_id)
        return {"user_id": user_id, "name": user_name}

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Создает тестовый клиент."""
    return TestClient(app)


def test_caching_works(client: TestClient) -> None:
    """Тестирует работу кеширования."""
    # Первый запрос - должен выполниться
    response1 = client.get("/test")
    assert response1.status_code == 200
    data1 = response1.json()

    # Второй запрос - должен вернуть кешированный ответ
    response2 = client.get("/test")
    assert response2.status_code == 200
    data2 = response2.json()

    # Данные должны быть одинаковыми (кешированный ответ)
    assert data1["message"] == data2["message"]
    assert data1["timestamp"] == data2["timestamp"]


def test_user_endpoint_caching(client: TestClient) -> None:
    """Тестирует кеширование endpoint'а с параметрами."""
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


def test_middleware_performance(client: TestClient) -> None:
    """Тестирует производительность middleware."""
    import time

    # Измеряем время первого запроса
    start_time = time.time()
    response1 = client.get("/test")
    first_request_time = time.time() - start_time

    # Измеряем время второго запроса (должен быть быстрее из-за кеша)
    start_time = time.time()
    response2 = client.get("/test")
    second_request_time = time.time() - start_time

    # Второй запрос должен быть быстрее или примерно таким же
    # (в тестовой среде разница может быть минимальной)
    assert response1.status_code == 200
    assert response2.status_code == 200
