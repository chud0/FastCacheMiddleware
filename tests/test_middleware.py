"""Тесты для оптимизированного FastCacheMiddleware."""

from fastapi.testclient import TestClient


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
