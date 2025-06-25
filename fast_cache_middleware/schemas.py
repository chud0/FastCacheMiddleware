import re
from typing import Any, Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from starlette.requests import Request
from starlette.routing import Route

from .depends import CacheConfig, CacheDropConfig


class CacheConfiguration(BaseModel):
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
    def one_of_field_is_set(self) -> "CacheConfiguration":
        if (
            self.max_age is None
            and self.key_func is None
            and self.invalidate_paths is None
        ):
            raise ValueError(
                "At least one of max_age, key_func, or invalidate_paths must be set."
            )
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


class RouteInfo(BaseModel):
    """Route information with cache configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    route: Route
    cache_config: CacheConfiguration

    @computed_field  # type: ignore[prop-decorator]
    @property
    def path(self) -> str:
        return getattr(self.route, "path", "")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def methods(self) -> set[str]:
        return getattr(self.route, "methods", set())
