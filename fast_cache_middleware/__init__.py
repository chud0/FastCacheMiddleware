"""FastCacheMiddleware - high-performance ASGI middleware for caching.

Route resolution approach:
- Route analysis at application startup
- Cache configuration extraction from FastAPI dependencies
- Efficient caching and invalidation based on routes


TODO:
 - add check for dependencies for middleware exists. and raise error if not.
 - automatically add x-cache-age to the OpenAPI schema (openapi_extra) based on caching dependency.
"""

from .controller import Controller
from .depends import BaseCacheConfigDepends, CacheConfig, CacheDropConfig
from .middleware import FastCacheMiddleware
from .storages import BaseStorage, InMemoryStorage

__version__ = "1.0.0"

__all__ = [
    # Main components
    "FastCacheMiddleware",
    "Controller",
    # Configuration via dependencies
    "CacheConfig",
    "CacheDropConfig",
    "BaseCacheConfigDepends",
    # Storages
    "BaseStorage",
    "InMemoryStorage",
    # Serialization
    "BaseSerializer",
    "DefaultSerializer",
]
