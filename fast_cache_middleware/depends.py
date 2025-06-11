from fastapi import Depends
import typing as tp
from starlette.requests import Request
from fastapi import params


class BaseCacheConfigDepends(params.Depends):
    """Базовый класс для конфигурации кеширования через ASGI scope extensions.

    Использует стандартизированный ASGI механизм extensions для передачи
    конфигурации от route dependencies к middleware.
    """

    use_cache: bool = True

    def __call__(self, request: Request) -> None:
        """Сохраняет конфигурацию в ASGI scope extensions.

        Args:
            request: HTTP запрос
        """
        # Используем стандартный ASGI extensions механизм
        if "extensions" not in request.scope:
            request.scope["extensions"] = {}

        if "fast_cache" not in request.scope["extensions"]:
            request.scope["extensions"]["fast_cache"] = {}

        request.scope["extensions"]["fast_cache"]["config"] = self

    @property
    def dependency(self) -> params.Depends:
        return self


class CacheConfig(BaseCacheConfigDepends):
    """Конфигурация кеширования для маршрута.

    Args:
        max_age: Время жизни кеша в секундах
        key_func: Функция генерации ключа кеша
    """

    def __init__(
        self,
        max_age: int = 5 * 60,
        key_func: tp.Optional[tp.Callable[[Request], str]] = None,
    ) -> None:
        self.max_age = max_age
        self.key_func = key_func


class CacheDropConfig(BaseCacheConfigDepends):
    """Конфигурация инвалидации кеша для маршрута.

    Args:
        paths: Пути для инвалидации кеша
    """

    def __init__(self, paths: tp.List[str]) -> None:
        self.paths = paths
