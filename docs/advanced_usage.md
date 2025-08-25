# 🛠️ Advanced Usage

!!! note 

    Sometimes the default caching behavior is not enough.  
    For these cases, **FastCacheMiddleware** allows you to plug in a custom `Controller` to fine-tune caching logic and cache key generation.


### Custom Controller

```py
from fast_cache_middleware import Controller

class CustomController(Controller):
    async def is_cachable_request(self, request):
        # Custom logic - don't cache admin requests
        if request.headers.get("x-admin-request"):
            return False
        return await super().should_cache_request(request)
    
    async def generate_cache_key(self, request):
        # Add API version to key
        version = request.headers.get("api-version", "v1")
        base_key = await super().generate_cache_key(request)
        return f"{version}:{base_key}"

app.add_middleware(
    FastCacheMiddleware,
    controller=CustomController()
)
```

---
**What this does**

* is_cachable_request: lets you decide dynamically whether a request should be cached. In this example, requests marked as x-admin-request bypass caching entirely, ensuring that admin users always see live data.
* generate_cache_key: allows you to customize how cache keys are constructed. Here, the api-version header is added to the cache key, which prevents collisions between different API versions.
---
**Why override the controller?**

A custom controller is useful when you need:


* Per-role logic: cache responses for public users but not for admins or staff.
* Multi-tenant isolation: include tenant_id or org_id in cache keys.
* API versioning: avoid reusing cached responses across different versions of your API.
* Custom invalidation strategies: override how and when entries are dropped.
* Security enforcement: skip caching for endpoints with sensitive headers or tokens.

---


✅ With a custom controller, you can implement project-specific rules while still reusing all the base middleware logic.