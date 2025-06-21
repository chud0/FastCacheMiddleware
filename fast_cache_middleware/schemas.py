import typing as tp

from starlette.routing import Route

from .depends import CacheConfig, CacheDropConfig


class RouteInfo:
    """Route information with cache configuration."""

    def __init__(
        self,
        route: Route,
        cache_config: CacheConfig | None = None,
        cache_drop_config: CacheDropConfig | None = None,
    ):
        self.route = route
        self.cache_config = cache_config
        self.cache_drop_config = cache_drop_config
        self.path: str = getattr(route, "path")
        self.methods: tp.Set[str] = getattr(route, "methods", set())
