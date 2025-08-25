# 🎯 Quick Start


## Step by step
---

1. Installing the package
```bash
pip install fast-cache-middleware
```
2. Importing necessary objects
```py
from fast_cache_middleware import CacheConfig, CacheDropConfig, FastCacheMiddleware
```
3. Add middleware;
```py
app.add_middleware(FastCacheMiddleware)
```
4. Attaching cache configuration as a FastAPI dependency
```python
dependencies=[CacheConfig(max_age=300)]
dependencies=[CacheDropConfig(paths=["/users/*", "/api/users/*"])]
```
5. Enjoy


## 📝 Examples

---
```py
import uvicorn
from fastapi import FastAPI

from fast_cache_middleware import CacheConfig, CacheDropConfig, FastCacheMiddleware

app = FastAPI()

# Add middleware - it will automatically analyze routes
app.add_middleware(FastCacheMiddleware)


# Routes with caching
@app.get("/users/{user_id}", dependencies=[CacheConfig(max_age=300)])
async def get_user(user_id: int) -> dict[str, int | str]:
    """This endpoint is cached for 5 minutes."""
    # Simulate database load
    return {"user_id": user_id, "name": f"User {user_id}"}


# Routes with cache invalidation
@app.post(
    "/users/{user_id}",
    dependencies=[CacheDropConfig(paths=["/users/*", "/api/users/*"])],
)
async def update_user(user_id: int) -> dict[str, int | str]:
    """It will invalidate cache for all /users/* paths."""
    return {"user_id": user_id, "status": "updated"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

More examples in the `examples/` [folder](https://github.com/chud0/FastCacheMiddleware/tree/main/examples):

- **quick_start.py** - minimal example showing basic caching and invalidation
- **basic.py** - basic usage with FastAPI
- **redis_example.py** - example with Redis