import typing as tp

from starlette.routing import Route

from .depends import BaseCacheConfigDepends


class RouteInfo:
    """Информация о роуте с кеш конфигурацией."""

    def __init__(
        self,
        route: Route,
        cache_config: tp.Optional[BaseCacheConfigDepends] = None,
        cache_drop_config: tp.Optional[BaseCacheConfigDepends] = None,
    ):
        self.route = route
        self.cache_config = cache_config
        self.cache_drop_config = cache_drop_config
        self.path: str = getattr(route, "path")
        self.methods: tp.Set[str] = getattr(route, "methods", set())
