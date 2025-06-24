from fastapi import routing, FastAPI
from fastapi.openapi.utils import get_openapi

from .depends import CacheConfig


def set_cache_age_in_openapi_schema(app: FastAPI) -> None:

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    for route in app.routes:
        if isinstance(route, routing.APIRoute):
            path = route.path
            methods = route.methods

            for dependency in route.dependant.dependencies:
                dep = dependency.call
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