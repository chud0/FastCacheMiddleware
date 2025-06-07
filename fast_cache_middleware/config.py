"""
Конфигурационные классы для FastCacheMiddleware.

Этот модуль определяет классы конфигурации для настройки кеширования и инвалидации.
"""
from typing import List, Optional, Type

from fastapi import Depends, Request
from pydantic import BaseModel, Field

from .types import (
    BaseCacheStore,
    CacheStoreType,
    CacheVisibility,
    HTTPMethod,
    KeyFunc,
    KeyTemplate,
    PathTemplate,
)


class CacheConfig(BaseModel):
    """
    Конфигурация кеширования для GET-запросов.

    Attributes:
        max_age: Время жизни кеша в секундах
        visibility: Видимость кеша (PUBLIC/PRIVATE)
        key_func: Функция генерации ключа кеша
        cache_store: Тип хранилища кеша
    """

    max_age: int = Field(
        default=300,
        description="Время жизни кеша в секундах",
        gt=0,
    )
    visibility: CacheVisibility = Field(
        default=CacheVisibility.PUBLIC,
        description="Видимость кеша",
    )
    key_func: KeyFunc = Field(
        ...,
        description="Функция генерации ключа кеша",
    )
    cache_store: Optional[CacheStoreType] = Field(
        default=None,
        description="Тип хранилища кеша",
    )

    class Config:
        """Конфигурация Pydantic модели."""

        arbitrary_types_allowed = True


class CacheDropConfig(BaseModel):
    """
    Конфигурация инвалидации для модифицирующих запросов.

    Attributes:
        paths: Список путей для инвалидации
        key_template: Шаблон ключа для массовой инвалидации
        on_methods: HTTP методы, триггерирующие инвалидацию
    """

    paths: List[PathTemplate] = Field(
        default_factory=list,
        description="Список путей для инвалидации",
    )
    key_template: Optional[KeyTemplate] = Field(
        default=None,
        description="Шаблон ключа для массовой инвалидации",
    )
    on_methods: List[HTTPMethod] = Field(
        default=["POST", "PUT", "PATCH", "DELETE"],
        description="HTTP методы, триггерирующие инвалидацию",
    )


def get_cache_config(
    request: Request,
    config: CacheConfig = Depends(),
) -> CacheConfig:
    """
    Dependency для получения конфигурации кеширования.

    Args:
        request: HTTP запрос
        config: Конфигурация кеширования

    Returns:
        Конфигурация кеширования
    """
    return config


def get_cache_drop_config(
    request: Request,
    config: CacheDropConfig = Depends(),
) -> CacheDropConfig:
    """
    Dependency для получения конфигурации инвалидации.

    Args:
        request: HTTP запрос
        config: Конфигурация инвалидации

    Returns:
        Конфигурация инвалидации
    """
    return config 