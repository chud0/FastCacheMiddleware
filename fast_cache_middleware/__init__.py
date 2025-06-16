"""FastCacheMiddleware - high-performance ASGI middleware for caching.

Route resolution approach:
- Route analysis at application startup
- Cache configuration extraction from FastAPI dependencies
- Efficient caching and invalidation based on routes
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
