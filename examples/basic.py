"""Базовый пример использования FastCacheMiddleware с резолюцией роутов.

Демонстрирует:
1. Анализ роутов на старте приложения
2. Извлечение кеш конфигураций из dependencies
3. Автоматическое кеширование GET запросов
4. Инвалидация кеша при модифицирующих запросах
"""

import asyncio
import logging
import time
import typing as tp

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from fast_cache_middleware import CacheConfig, CacheDropConfig, FastCacheMiddleware

# Создаем FastAPI приложение
app = FastAPI(title="FastCacheMiddleware Basic Example")

# Добавляем middleware - он проанализирует роуты при первом запросе
app.add_middleware(FastCacheMiddleware)


def custom_key_func(request: Request) -> str:
    # Ключ включает user-id из заголовков если есть
    user_id = request.headers.get("user-id", "anonymous")
    return f"{request.url.path}:user:{user_id}"


class User(BaseModel):
    name: str
    email: str


class FullUser(User):
    user_id: int


class UserResponse(FullUser):
    timestamp: float = Field(default_factory=time.time)


_USERS_STORAGE: tp.Dict[int, User] = {
    1: User(name="John Doe", email="john.doe@example.com"),
    2: User(name="Jane Doe", email="jane.doe@example.com"),
}


# Роуты с различными конфигурациями кеширования


@app.get("/")
async def root() -> tp.Dict[str, tp.Union[str, float]]:
    """Корневой роут без кеширования."""
    return {
        "message": "Without cache response",
        "timestamp": time.time(),
        "cache_duration": "0 seconds",
    }


@app.get(
    "/fast", dependencies=[CacheConfig(max_age=30)], openapi_extra={"x-cache-age": 30}
)
async def fast_endpoint() -> tp.Dict[str, tp.Union[str, float]]:
    """Быстрый endpoint с коротким кешированием (30 секунд)."""

    return {
        "message": "Fast cached response",
        "timestamp": time.time(),
        "cache_duration": "30 seconds",
    }


@app.get(
    "/slow", dependencies=[CacheConfig(max_age=300)], openapi_extra={"x-cache-age": 300}
)
async def slow_endpoint() -> tp.Dict[str, tp.Union[str, float]]:
    """Медленный endpoint с длинным кешированием (5 минут)."""
    await asyncio.sleep(0.5)

    return {
        "message": "Slow cached response",
        "timestamp": time.time(),
        "cache_duration": "300 seconds",
    }


@app.get(
    "/users/{user_id}",
    dependencies=[CacheConfig(max_age=60, key_func=custom_key_func)],
)
async def get_user(user_id: int) -> UserResponse:
    """Получение пользователя с кастомным ключом кеширования.

    Ключ кеша включает user-id из заголовков для персонализации.
    """
    user = _USERS_STORAGE.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(user_id=user_id, name=user.name, email=user.email)


@app.get("/users", dependencies=[CacheConfig(max_age=30)])
async def get_users() -> tp.List[UserResponse]:
    return [
        UserResponse(user_id=user_id, name=user.name, email=user.email)
        for user_id, user in _USERS_STORAGE.items()
    ]


@app.post("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users"])])
async def create_user(user_id: int, user_data: User) -> UserResponse:
    """Создание пользователя с инвалидацией кеша.

    Этот POST запрос инвалидирует кеш для всех /users/* путей.
    """
    _USERS_STORAGE[user_id] = user_data

    return UserResponse(user_id=user_id, name=user_data.name, email=user_data.email)


@app.put("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users"])])
async def update_user(user_id: int, user_data: User) -> UserResponse:
    """Обновление пользователя с инвалидацией кеша."""
    user = _USERS_STORAGE.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _USERS_STORAGE[user_id] = user_data

    return UserResponse(user_id=user_id, name=user_data.name, email=user_data.email)


@app.delete("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users"])])
async def delete_user(user_id: int) -> UserResponse:
    """Удаление пользователя с инвалидацией кеша."""
    user = _USERS_STORAGE.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    del _USERS_STORAGE[user_id]

    return UserResponse(user_id=user_id, name=user.name, email=user.email)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("🚀 Запуск FastCacheMiddleware Basic Example...")
    print("\n📋 Доступные endpoints:")
    print("   GET /                    - корневой роут (без кеша)")
    print("   GET /fast               - короткий кеш (30s)")
    print("   GET /slow               - длинный кеш (5m)")
    print("   GET /users/{user_id}    - получение пользователя (кеш 3 мин)")
    print("   GET /users              - список пользователей (кеш 3 мин)")
    print("   POST /users/{user_id}   - создание пользователя (инвалидация /users)")
    print(
        "   PUT /users/{user_id}    - обновление пользователя (инвалидация /users и /users/*)"
    )
    print("   DELETE /users/{user_id} - удаление пользователя (инвалидация /users)")

    print("\n🔧 Как работает middleware:")
    print("   1. При старте анализирует все роуты")
    print("   2. Извлекает CacheConfig/CacheDropConfig из dependencies")
    print("   3. При запросе находит соответствующий роут")
    print("   4. Применяет кеширование согласно конфигурации")

    print("\n💡 Для тестирования:")
    print("   curl http://localhost:8000/users/1")
    print("   curl http://localhost:8000/users")
    print(
        '   curl -X POST http://localhost:8000/users/1 -H "Content-Type: application/json" -d \'{"name": "John", "email": "john@example.com"}\''
    )
    print(
        '   curl -X PUT http://localhost:8000/users/1 -H "Content-Type: application/json" -d \'{"name": "John Updated", "email": "john@example.com"}\''
    )
    print("   curl -X DELETE http://localhost:8000/users/1")

    uvicorn.run(app, host="127.0.0.1", port=8000)
