# 🎛️ Storages

FastCacheMiddleware abstracts the cache layer behind a simple storage interface. You can start with the built-in **InMemoryStorage** and switch to **RedisStorage** (or any custom backend) without changing your routes.

Key ideas:

- **Latency vs. scope**: in-memory is fastest but limited to a single process; Redis is slightly slower but shared across workers/hosts.
- **Eviction & TTL**: storages should support TTL and a predictable eviction policy to keep memory under control.
- **Serialization**: responses are serialized before storing; choose a format that balances speed and size.

---

### InMemoryStorage (default)

```python
from fast_cache_middleware import FastCacheMiddleware, InMemoryStorage

storage = InMemoryStorage(max_size=1000)
app.add_middleware(FastCacheMiddleware, storage=storage)
```
**What it is**: ultra-low-latency cache that lives inside the Python process.

**When to use**

* Single-process or single-worker deployments.
* Read-heavy endpoints where every microsecond matters.
* Local development and integration tests.

**Behavior**

* Stores entries in the app process; other workers/instances won’t see the same cache.
* Uses batch cleanup (compacting/evicting in chunks) to reduce lock contention and GC pressure at high RPS.
* Eviction is typically LRU-like under max_size pressure; tune max_size to your memory budget.

**Trade-offs**

* ⚡ Fastest possible hits (sub-millisecond).
* ❌ No cross-process sharing: with uvicorn --workers N каждый воркер держит свой кэш.
* ❌ Cache is lost on restart/redeploy.

!!! tip
    * Prefer short/medium TTLs; don’t let large responses accumulate unchecked.
    * If you run multiple workers and need consistency, consider Redis.

---
### RedisStorage

```python
from fast_cache_middleware import RedisStorage
redis = Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)
app.add_middleware(FastCacheMiddleware, storage=RedisStorage(redis_client=redis))
```
**What it is**: networked cache shared by all app workers and hosts.

**When to use**

* Horizontal scaling (multiple workers/containers/servers).
* You need consistent cache view, shared invalidation, or warm-up across instances.
* Coordinated CacheDrop across the fleet.

**Behavior**

* Keys are namespaced (recommend a prefix like fcm:) and stored with TTL.
* Slight network overhead (usually +0.3–1.5 ms per hit), but massive gains from sharing.

**Best practices**

* Enable connection pooling and timeouts on the Redis client.
* Use EXPIRE/TTL on every set; never store without TTL.
* Keep values compact: JSON (fast to debug) or msgpack (faster/smaller); avoid heavy pickles for public APIs.
* Monitor memory (used_memory, evicted_keys) and keyspace hits/misses to watch your hit ratio.

**Trade-offs**

* ⚖️ Small latency overhead vs. in-memory.
* ✅ Cross-process coherence and centralized invalidation.
* ✅ Survives app restarts (until TTL).

---
### Custom Storage

```python
from fast_cache_middleware import BaseStorage

class RedisStorage(BaseStorage):
    def __init__(self, redis_url: str):
        import redis
        self.redis = redis.from_url(redis_url)
    
    async def store(self, key: str, response, request, metadata):
        # Implementation for saving to Redis
        pass
    
    async def retrieve(self, key: str):
        # Implementation for retrieving from Redis
        pass

app.add_middleware(FastCacheMiddleware, storage=RedisStorage("redis://localhost"))
```
**How to implement**

* Inherit from BaseStorage and implement at least:
  * store(key, response, request, metadata) — serialize and persist with TTL from metadata.
  * retrieve(key) — return the raw serialized blob (the middleware will deserialize), or None.

**Design guidelines**

* Serialization: choose a stable format. Include response status, headers subset, and body.
* TTL & eviction: apply TTL on write; for size-bounded stores add an eviction policy (LRU/LFU).
* Key schema: include route, method, and the computed key_func part; use a clear prefix (e.g., fcm:v1:).
* Observability: expose counters (hits/misses/evictions) and latency histograms per backend.
* Safety: validate sizes (reject too-large payloads), and avoid caching non-idempotent responses.

---
## Choosing the right backend
| Scenario                               | Recommended storage | Why                                |
|----------------------------------------|---------------------|------------------------------------|
| Dev / single worker                    | InMemoryStorage     | Zero setup, fastest                |
| Multiple workers / containers          | RedisStorage        | Shared cache + shared invalidation |
| Large payloads, strict memory caps     | RedisStorage        | Centralized limits & eviction      |
| Cross-service reuse (edge/API gateway) | RedisStorage        | Warm cache across apps             |

!!! tip "**Rule of thumb**"
    Start with **InMemory** for simplicity; move to **Redis** as soon as you scale horizontally or need consistent invalidation across instances.