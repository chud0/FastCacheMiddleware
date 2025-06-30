from fastapi import FastAPI, routing

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
