# 📊 Performance

### Benchmarks

- **Route analysis**: ~5ms for 100 routes at startup
- **Route lookup**: ~0.1ms per request (O(n) by number of cached routes)
- **Cache hit**: ~1ms per request
- **Cache miss**: original request time + ~2ms for saving

### Optimization

```python
# For applications with many routes
app.add_middleware(
    FastCacheMiddleware,
    storage=InMemoryStorage(max_size=10000),  # Increase cache size
    controller=Controller(default_ttl=3600)   # Increase default TTL
)
```