import typing as tp

from fastapi import FastAPI, routing
from starlette.routing import Mount

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


def get_app_routes(app: FastAPI) -> tp.List[routing.APIRoute]:
    """Gets all routes from FastAPI application.

    Recursively traverses all application routers and collects their routes.

    Args:
        app: FastAPI application

    Returns:
        List of all application routes
    """
    routes = []

    # Get routes from main application router
    routes.extend(get_routes(app.router))

    # Traverse all nested routers
    for route in app.router.routes:
        if isinstance(route, Mount):
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes


def get_routes(router: routing.APIRouter) -> list[routing.APIRoute]:
    """Recursively gets all routes from router.

    Traverses all routes in router and its sub-routers, collecting them into a single list.

    Args:
        router: APIRouter to traverse

    Returns:
        List of all routes from router and its sub-routers
    """
    routes = []

    # Get all routes from current router
    for route in router.routes:
        if isinstance(route, routing.APIRoute):
            routes.append(route)
        elif isinstance(route, Mount):
            # Recursively traverse sub-routers
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes
