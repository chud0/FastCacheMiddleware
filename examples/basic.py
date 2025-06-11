"""Базовый пример использования FastCacheMiddleware с резолюцией роутов.

Демонстрирует:
1. Анализ роутов на старте приложения
2. Извлечение кеш конфигураций из dependencies
3. Автоматическое кеширование GET запросов
4. Инвалидация кеша при модифицирующих запросах
"""

from fastapi import FastAPI, Depends
from fast_cache_middleware import FastCacheMiddleware, CacheConfig, CacheDropConfig
import time
import uvicorn


# Создаем FastAPI приложение
app = FastAPI(title="FastCacheMiddleware Basic Example")

# Добавляем middleware - он проанализирует роуты при первом запросе
app.add_middleware(FastCacheMiddleware)


# Функции для создания кеш конфигураций
def short_cache() -> CacheConfig:
    """Короткое кеширование - 30 секунд."""
    return CacheConfig(max_age=30)


def long_cache() -> CacheConfig:
    """Длинное кеширование - 5 минут."""
    return CacheConfig(max_age=300)


def custom_key_cache() -> CacheConfig:
    """Кеширование с кастомной функцией ключа."""

    def custom_key_func(request):
        # Ключ включает user-id из заголовков если есть
        user_id = request.headers.get("user-id", "anonymous")
        return f"{request.url.path}:user:{user_id}"

    return CacheConfig(max_age=60, key_func=custom_key_func)


def invalidate_users_cache() -> CacheDropConfig:
    """Конфигурация для инвалидации кеша пользователей."""
    return CacheDropConfig(paths=["/users/*", "/user/*"])


# Роуты с различными конфигурациями кеширования


@app.get("/")
async def root():
    """Корневой роут без кеширования."""
    return {"message": "FastCacheMiddleware Basic Example", "timestamp": time.time()}


@app.get("/fast", dependencies=[CacheConfig(max_age=30)])
async def fast_endpoint():
    """Быстрый endpoint с коротким кешированием (30 секунд).

    Middleware анализирует dependencies и находит CacheConfig.
    При первом запросе ответ кешируется на 30 секунд.
    """
    return {
        "message": "Fast cached response",
        "timestamp": time.time(),
        "cache_duration": "30 seconds",
    }


@app.get("/slow", dependencies=[CacheConfig(max_age=300)])
async def slow_endpoint():
    """Медленный endpoint с длинным кешированием (5 минут)."""
    # Имитируем медленное вычисление
    import asyncio

    await asyncio.sleep(0.5)

    return {
        "message": "Slow cached response",
        "timestamp": time.time(),
        "cache_duration": "5 minutes",
        "computed": True,
    }


@app.get(
    "/users/{user_id}",
    dependencies=[CacheConfig(max_age=60, key_func=custom_key_cache)],
)
async def get_user(user_id: int):
    """Получение пользователя с кастомным ключом кеширования.

    Ключ кеша включает user-id из заголовков для персонализации.
    """
    # Имитируем загрузку из базы данных
    import asyncio

    await asyncio.sleep(0.2)

    return {
        "user_id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com",
        "timestamp": time.time(),
    }


@app.get("/data/{item_id}", dependencies=[CacheConfig(max_age=300)])
async def get_data(item_id: str):
    """Получение данных с длинным кешированием."""
    return {
        "item_id": item_id,
        "data": f"Some data for {item_id}",
        "timestamp": time.time(),
    }


# Роуты для модификации с инвалидацией кеша


@app.post(
    "/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users/*", "/user/*"])]
)
async def update_user(user_id: int, user_data: dict):
    """Обновление пользователя с инвалидацией кеша.

    Этот POST запрос инвалидирует кеш для всех /users/* путей.
    """
    return {
        "user_id": user_id,
        "message": "User updated",
        "cache_invalidated": True,
        "timestamp": time.time(),
    }


@app.delete(
    "/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users/*", "/user/*"])]
)
async def delete_user(user_id: int):
    """Удаление пользователя с инвалидацией кеша."""
    return {
        "user_id": user_id,
        "message": "User deleted",
        "cache_invalidated": True,
        "timestamp": time.time(),
    }


@app.get("/stats")
async def get_stats():
    """Статистика (не кешируется)."""
    return {
        "total_requests": "dynamic",
        "cache_hits": "dynamic",
        "timestamp": time.time(),
        "note": "This endpoint is not cached",
    }


# Демонстрационные роуты для тестирования


@app.get("/test/cache-headers")
async def test_cache_headers():
    """Тестирование заголовков кеширования."""
    from starlette.responses import JSONResponse

    response = JSONResponse(
        {"message": "Response with cache headers", "timestamp": time.time()}
    )

    # Добавляем заголовки кеширования
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["ETag"] = '"test-etag-123"'

    return response


if __name__ == "__main__":
    print("🚀 Запуск FastCacheMiddleware Basic Example...")
    print("\n📋 Доступные endpoints:")
    print("   GET /                    - корневой роут (без кеша)")
    print("   GET /fast               - короткий кеш (30s)")
    print("   GET /slow               - длинный кеш (5m)")
    print("   GET /users/{user_id}    - кастомный ключ кеша")
    print("   GET /data/{item_id}     - длинный кеш (5m)")
    print("   POST /users/{user_id}   - обновление с инвалидацией")
    print("   DELETE /users/{user_id} - удаление с инвалидацией")
    print("   GET /stats              - без кеша")
    print("   GET /test/cache-headers - тест заголовков")

    print("\n🔧 Как работает middleware:")
    print("   1. При старте анализирует все роуты")
    print("   2. Извлекает CacheConfig/CacheDropConfig из dependencies")
    print("   3. При запросе находит соответствующий роут")
    print("   4. Применяет кеширование согласно конфигурации")

    print("\n💡 Для тестирования:")
    print("   curl http://localhost:8000/fast")
    print("   curl -H 'user-id: 123' http://localhost:8000/users/1")
    print("   curl -X POST http://localhost:8000/users/1 -d '{}'")

    uvicorn.run(app, host="127.0.0.1", port=8000)
