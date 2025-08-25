# 🔒 Security

### Cache Isolation

```python
def user_specific_cache() -> CacheConfig:
    def secure_key_func(request):
        # Include user token in key
        token = request.headers.get("authorization", "").split(" ")[-1]
        return f"{request.url.path}:token:{token}"
    
    return CacheConfig(max_age=300, key_func=secure_key_func)

@app.get("/private/data", dependencies=[Depends(user_specific_cache)])
async def get_private_data():
    return {"sensitive": "data"}
```

### Header Validation

Middleware automatically respects standard HTTP caching headers:

- `Cache-Control: no-cache` - skip cache
- `Cache-Control: no-store` - forbid caching
- `Cache-Control: private`  - don't cache private responses
