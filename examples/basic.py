"""
Базовый пример использования FastCacheMiddleware.

Этот пример демонстрирует базовое использование middleware
для кеширования ответов API.
"""
import asyncio
from typing import Dict, List

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware

from ..core.config import CacheConfig, CacheDropConfig, CacheVisibility
from ..core.middleware import FastCacheMiddleware
from ..stores.memory import MemoryCacheStore


app = FastAPI(
    title="FastCacheMiddleware Example",
    description="Пример использования FastCacheMiddleware",
    version="0.1.0",
    middleware=[
        Middleware(
            FastCacheMiddleware,
            default_store=MemoryCacheStore(),
        ),
    ],
)


# Мок база данных
db: Dict[str, Dict] = {
    "users": {
        "1": {"id": "1", "name": "John Doe", "email": "john@example.com"},
        "2": {"id": "2", "name": "Jane Smith", "email": "jane@example.com"},
    },
    "posts": {
        "1": {"id": "1", "title": "First Post", "content": "Hello, World!"},
        "2": {"id": "2", "title": "Second Post", "content": "Another post"},
    },
}


@app.get(
    "/users/{user_id}",
    dependencies=[
        Depends(
            CacheConfig(
                max_age=300,
                visibility=CacheVisibility.PRIVATE,
                key_func=lambda r: f"user_{r.path_params['user_id']}",
            )
        )
    ],
)
async def get_user(user_id: str) -> JSONResponse:
    """
    Получить информацию о пользователе.

    Args:
        user_id: ID пользователя

    Returns:
        Информация о пользователе
    """
    if user_id not in db["users"]:
        return JSONResponse(
            status_code=404,
            content={"detail": "User not found"},
        )
    return JSONResponse(content=db["users"][user_id])


@app.get(
    "/users",
    dependencies=[
        Depends(
            CacheConfig(
                max_age=300,
                visibility=CacheVisibility.PRIVATE,
                key_func=lambda r: "users_list",
            )
        )
    ],
)
async def list_users() -> JSONResponse:
    """
    Получить список всех пользователей.

    Returns:
        Список пользователей
    """
    return JSONResponse(content=list(db["users"].values()))


@app.post(
    "/users",
    dependencies=[
        Depends(
            CacheDropConfig(
                paths=["/users", "/users/{user_id}"],
                key_template="user_{id}",
            )
        )
    ],
)
async def create_user(request: Request) -> JSONResponse:
    """
    Создать нового пользователя.

    Args:
        request: HTTP запрос с данными пользователя

    Returns:
        Созданный пользователь
    """
    user_data = await request.json()
    user_id = str(len(db["users"]) + 1)
    user = {"id": user_id, **user_data}
    db["users"][user_id] = user
    return JSONResponse(
        status_code=201,
        content=user,
    )


@app.get(
    "/posts/{post_id}",
    dependencies=[
        Depends(
            CacheConfig(
                max_age=300,
                visibility=CacheVisibility.PUBLIC,
                key_func=lambda r: f"post_{r.path_params['post_id']}",
            )
        )
    ],
)
async def get_post(post_id: str) -> JSONResponse:
    """
    Получить информацию о посте.

    Args:
        post_id: ID поста

    Returns:
        Информация о посте
    """
    if post_id not in db["posts"]:
        return JSONResponse(
            status_code=404,
            content={"detail": "Post not found"},
        )
    return JSONResponse(content=db["posts"][post_id])


@app.get(
    "/posts",
    dependencies=[
        Depends(
            CacheConfig(
                max_age=300,
                visibility=CacheVisibility.PUBLIC,
                key_func=lambda r: "posts_list",
            )
        )
    ],
)
async def list_posts() -> JSONResponse:
    """
    Получить список всех постов.

    Returns:
        Список постов
    """
    return JSONResponse(content=list(db["posts"].values()))


@app.post(
    "/posts",
    dependencies=[
        Depends(
            CacheDropConfig(
                paths=["/posts", "/posts/{post_id}"],
                key_template="post_{id}",
            )
        )
    ],
)
async def create_post(request: Request) -> JSONResponse:
    """
    Создать новый пост.

    Args:
        request: HTTP запрос с данными поста

    Returns:
        Созданный пост
    """
    post_data = await request.json()
    post_id = str(len(db["posts"]) + 1)
    post = {"id": post_id, **post_data}
    db["posts"][post_id] = post
    return JSONResponse(
        status_code=201,
        content=post,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "basic:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    ) 