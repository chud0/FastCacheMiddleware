"""
FastCacheMiddleware - интеллектуальное middleware для кеширования ответов FastAPI.

Этот пакет предоставляет middleware для кеширования ответов FastAPI
с гибкой настройкой и автоматической инвалидацией.
"""

from .config import CacheConfig, CacheDropConfig, CacheVisibility
from .middleware import FastCacheMiddleware
from .route import CacheAPIRoute, CacheAPIRouter
from .types import BaseCacheStore, CacheKey, CacheValue
from .stores.base import AbstractCacheStore
from .stores.memory import MemoryCacheStore

__version__ = "0.1.0"

__all__ = [
    "FastCacheMiddleware",
    "CacheConfig",
    "CacheDropConfig",
    "CacheVisibility",
    "CacheAPIRoute",
    "CacheAPIRouter",
    "BaseCacheStore",
    "AbstractCacheStore",
    "MemoryCacheStore",
    "CacheKey",
    "CacheValue",
] 