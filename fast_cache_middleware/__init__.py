"""FastCacheMiddleware - высокопроизводительный ASGI middleware для кеширования.

Подход с резолюцией роутов:
- Анализ роутов на старте приложения
- Извлечение кеш конфигураций из FastAPI dependencies
- Эффективное кеширование и инвалидация на основе роутов
"""

from .middleware import FastCacheMiddleware
from .controller import Controller
from .depends import CacheConfig, CacheDropConfig, BaseCacheConfigDepends
from .storages import BaseStorage, InMemoryStorage
from .serializers import BaseSerializer

__version__ = "1.0.0"

__all__ = [
    # Основные компоненты
    "FastCacheMiddleware",
    "Controller",
    # Конфигурация через dependencies
    "CacheConfig",
    "CacheDropConfig",
    "BaseCacheConfigDepends",
    # Хранилища
    "BaseStorage",
    "InMemoryStorage",
    # Сериализация
    "BaseSerializer",
    "DefaultSerializer",
]
