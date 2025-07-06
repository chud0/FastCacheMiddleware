"""An example of using Fast Cache Middleware with rout resolution and Redis storage.

to install using Redis, run this command: pip install fast-cache-middleware[redis]

Demonstrates:
1. Analysis of routes at the start of the application;
2. Extracting configuration cache from dependencies;
3. Automatic caching of GET requests in Redis;
4. Cache invalidation in case of modifying requests.
"""

import logging
import time
import typing as tp

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis  # async only

from fast_cache_middleware import (
    CacheConfig,
    CacheDropConfig,
    FastCacheMiddleware,
    RedisStorage,
)

# Creating a Flash API application
app = FastAPI(title="FastCacheMiddleware Redis Example")
# Initializing Redis
redis = Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)

# Adding middleware - it will analyze the routes at the first request.
app.add_middleware(FastCacheMiddleware, storage=RedisStorage(redis_client=redis))


def custom_key_func(request: Request) -> str:
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


# Routers with different caching configurations


@app.get(
    "/users/{user_id}",
    dependencies=[CacheConfig(max_age=120, key_func=custom_key_func)],
)
async def get_user(user_id: int) -> UserResponse:
    """Getting a user with a custom caching key.

    The cache key includes the user-id from the headers for personalization.
    """
    user = _USERS_STORAGE.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(user_id=user_id, name=user.name, email=user.email)


@app.get("/users", dependencies=[CacheConfig(max_age=120)])
async def get_users() -> tp.List[UserResponse]:
    return [
        UserResponse(user_id=user_id, name=user.name, email=user.email)
        for user_id, user in _USERS_STORAGE.items()
    ]


@app.post("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users"])])
async def create_user(user_id: int, user_data: User) -> UserResponse:
    """Creating a user with a cache disability.

    This POST request disables the cache for all /users/* paths.
    """
    _USERS_STORAGE[user_id] = user_data

    return UserResponse(user_id=user_id, name=user_data.name, email=user_data.email)


@app.delete("/users/{user_id}", dependencies=[CacheDropConfig(paths=["/users"])])
async def delete_user(user_id: int) -> UserResponse:
    """Deleting a user with a cache disability.

    This DELETE request disables the cache for all /users/* paths.
    """
    user = _USERS_STORAGE.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    del _USERS_STORAGE[user_id]

    return UserResponse(user_id=user_id, name=user.name, email=user.email)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="[-] %(asctime)s [%(levelname)s] %(module)s-%(lineno)d - %(message)s",
    )

    print("🚀 Running Fast Cache Middleware Redis Example...")
    print("\n📋 Available endpoints:")
    print("   GET /users/{user_id}    - getting the user (2 min cache)")
    print("   GET /users              - list of users (2 min cache)")
    print("   POST /users/{user_id}   - user creation (disability /users)")
    print("   DELETE /users/{user_id} - deleting a user (invalidation /users)")

    print("\n💡 For testing purposes:")
    print("   curl http://localhost:8000/users/1")
    print("   curl http://localhost:8000/users")
    print(
        '   curl -X POST http://localhost:8000/users/1 -H "Content-Type: application/json" -d \'{"name": "John", "email": "john@example.com"}\''
    )
    print("   curl -X DELETE http://localhost:8000/users/1")
    print()

    uvicorn.run(app, host="127.0.0.1", port=8000)
