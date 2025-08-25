# 🔧 Configuration

FastCacheMiddleware provides two main dependency classes for configuration:  
- **CacheConfig** – controls how and when responses are cached for `GET` requests.  
- **CacheDropConfig** – defines invalidation rules for `POST`, `PUT`, and `DELETE` requests.  

These configurations are added as **FastAPI dependencies**, which makes them easy to declare directly in your routes.

---

### CacheConfig

Use `CacheConfig` to enable caching for a route.  
The simplest form is just setting a **time-to-live (TTL)** in seconds.

For more advanced scenarios, you can define a custom key function.
This allows you to personalize caching based on user identity, request headers, query parameters, etc.:

```py
from fast_cache_middleware import CacheConfig

# Simple caching
CacheConfig(max_age=300)  # 5 minutes

# With custom key function, for personalized cache
def key_func(request: Request):
    user_id = request.headers.get("Authorization", "anonymous")
    path = request.url.path
    query = str(request.query_params)
    return f"{path}:{user_id}:{query}"

CacheConfig(max_age=600, key_func=key_func)  # 10 minutes
```

---

### CacheDropConfig

Use CacheDropConfig to invalidate cache entries when data is modified by POST, PUT, or DELETE requests.
This ensures that users always see fresh data after an update.


```python
# Paths can be matched by startswith
CacheDropConfig(
    paths=[
        "/users/",  # Will match /users/123, /users/profile, etc.
        "/api/",    # Will match all API paths
    ]
)

# Paths can be matched by regexp
CacheDropConfig(
    paths=[
        r"^/users/\d+$",  # Will match /users/123, /users/456, etc.
        r"^/api/.*",      # Will match all API paths
    ]
)

# You can mix regexp and simple string matching - use what's more convenient
CacheDropConfig(
    paths=[
        "/users/",        # Simple prefix match
        r"^/api/\w+/\d+$" # Regexp for specific API endpoints
    ]
)
```

Key takeaways:
* Paths can be defined as string prefixes or regular expressions.
* Multiple paths can be combined in a single configuration.
* Use simple strings for convenience, regex for fine-grained control.
* With these two building blocks, you can fine-tune caching so that:
* Reads (GET) are fast and efficient.
* Writes (POST, PUT, DELETE) automatically keep the cache consistent.