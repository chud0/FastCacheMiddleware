from hashlib import blake2b

from fastapi import FastAPI, routing
from starlette.requests import Request

from .depends import CacheConfig


def set_cache_age_in_openapi_schema(app: FastAPI) -> None:
    openapi_schema = app.openapi()

    for route in app.routes:
        if isinstance(route, routing.APIRoute):
            path = route.path
            methods = route.methods

            for dependency in route.dependencies:
                dep = dependency.dependency
                if isinstance(dep, CacheConfig):
                    max_age = dep.max_age

                    for method in methods:
                        method = method.lower()
                        try:
                            operation = openapi_schema["paths"][path][method]
                            operation.setdefault("x-cache-age", max_age)
                        except KeyError:
                            continue

    app.openapi_schema = openapi_schema
    return None


def generate_key(request: Request) -> str:
    """Generates fast unique key for caching HTTP request.

    Args:
        request: Starlette Request object.

    Returns:
        str: Unique key for caching, based on request method and path.
        Uses fast blake2b hashing algorithm.

    Note:
        Does not consider scheme and host, as requests usually go to the same host.
        Only considers method, path and query parameters for maximum performance.
    """
    # Get only necessary components from scope
    scope = request.scope
    url = scope["path"]
    if scope["query_string"]:
        url += f"?{scope['query_string'].decode('ascii')}"

    # Use fast blake2b algorithm with minimal digest size
    key = blake2b(digest_size=8)
    key.update(request.method.encode())
    key.update(url.encode())

    return key.hexdigest()
