"""
Кастомный APIRoute для извлечения зависимостей.

Этот модуль определяет кастомный APIRoute для извлечения
зависимостей кеширования из роутов.
"""
from typing import Any, Callable, Dict, List, Optional, Type, Union

from fastapi import APIRouter, Depends, Request
from fastapi.routing import APIRoute
from starlette.responses import Response
from starlette.types import ASGIApp

from .config import CacheConfig, CacheDropConfig


class CacheAPIRoute(APIRoute):
    """
    Кастомный APIRoute для извлечения зависимостей кеширования.

    Этот класс расширяет стандартный APIRoute для поддержки
    извлечения зависимостей кеширования из роутов.
    """

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        dependencies: Optional[List[Depends]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Инициализация роута.

        Args:
            path: Путь роута
            endpoint: Обработчик роута
            dependencies: Список зависимостей
            **kwargs: Дополнительные параметры
        """
        super().__init__(
            path=path,
            endpoint=endpoint,
            dependencies=dependencies,
            **kwargs,
        )

        # Извлекаем конфигурации кеширования из зависимостей
        self.cache_config = self._extract_cache_config(dependencies)
        self.cache_drop_config = self._extract_cache_drop_config(dependencies)

    def _extract_cache_config(
        self,
        dependencies: Optional[List[Depends]],
    ) -> Optional[CacheConfig]:
        """
        Извлечь конфигурацию кеширования из зависимостей.

        Args:
            dependencies: Список зависимостей

        Returns:
            Конфигурация кеширования или None
        """
        if not dependencies:
            return None

        for dependency in dependencies:
            if isinstance(dependency.dependency, CacheConfig):
                return dependency.dependency

        return None

    def _extract_cache_drop_config(
        self,
        dependencies: Optional[List[Depends]],
    ) -> Optional[CacheDropConfig]:
        """
        Извлечь конфигурацию инвалидации из зависимостей.

        Args:
            dependencies: Список зависимостей

        Returns:
            Конфигурация инвалидации или None
        """
        if not dependencies:
            return None

        for dependency in dependencies:
            if isinstance(dependency.dependency, CacheDropConfig):
                return dependency.dependency

        return None


class CacheAPIRouter(APIRouter):
    """
    Кастомный APIRouter с поддержкой кеширования.

    Этот класс расширяет стандартный APIRouter для использования
    CacheAPIRoute вместо стандартного APIRoute.
    """

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Инициализация роутера.

        Args:
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы
        """
        kwargs["route_class"] = CacheAPIRoute
        super().__init__(*args, **kwargs) 