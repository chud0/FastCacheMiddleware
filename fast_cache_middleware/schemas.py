import re
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.requests import Request
from starlette.routing import Route

from .depends import CacheConfig, CacheDropConfig


class CacheConfigSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    max_age: int | None = Field(
        default=None,
        description="Cache lifetime in seconds. If None, caching is disabled.",
    )
    key_func: Callable[[Request], str] | None = Field(
        default=None,
        description="Custom cache key generation function. If None, default key generation is used.",
    )
    invalidate_paths: list[re.Pattern] | None = Field(
        default=None,
        description="Paths for cache invalidation (strings or regex patterns). No invalidation if None.",
    )

    @model_validator(mode="after")
    def one_of_field_is_set(self) -> "CacheConfigSchema":
        if self.max_age is None and self.key_func is None:
            raise ValueError("At least one of max_age or key_func must be set.")
        return self

    @field_validator("invalidate_paths")
    @classmethod
    def compile_paths(cls, item: Any) -> Any:
        if item is None:
            return None
        if isinstance(item, str):
            return re.compile(f"^{item}")
        if isinstance(item, re.Pattern):
            return item
        if isinstance(item, list):
            return [cls.compile_paths(i) for i in item]
        raise ValueError(
            "invalidate_paths must be a string, regex pattern, or list of them."
        )


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
        self.methods: set[str] = getattr(route, "methods", set())
