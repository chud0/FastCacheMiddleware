"""
Хранилища кеша для FastCacheMiddleware.

Этот модуль содержит реализации хранилищ кеша:
- Абстрактный базовый класс
- In-memory хранилище
"""

from .base import AbstractCacheStore
from .memory import MemoryCacheStore

__all__ = [
    "AbstractCacheStore",
    "MemoryCacheStore",
] 