# Welcome!

🚀 **High-performance ASGI middleware for caching with route resolution approach**

[![PyPI version](https://img.shields.io/pypi/v/fast-cache-middleware)](https://pypi.org/project/fast-cache-middleware/)
[![CI](https://github.com/chud0/FastCacheMiddleware/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/chud0/FastCacheMiddleware/actions/workflows/ci.yml)

## 📦 Installation

```bash
pip install fast-cache-middleware
```

## ✨ Key Features

FastCacheMiddleware uses a **route resolution approach** - it analyzes application routes at startup and extracts cache configurations from FastAPI dependencies.

### 🔧 How it works

1. **At application startup:**
   - Middleware analyzes all routes and their dependencies
   - Extracts `CacheConfig` and `CacheDropConfig` from dependencies
   - Creates internal route index with caching configurations

2. **During request processing:**
   - Checks HTTP method (cache only GET, invalidate for POST/PUT/DELETE)
   - Finds matching route by path and method
   - Extracts cache configuration from pre-analyzed dependencies
   - Performs caching or invalidation according to configuration

### 💡 Benefits

- **⚡ High performance** - pre-route analysis
- **🎯 Easy integration** - standard FastAPI dependencies
- **🔧 Flexible configuration** - custom key functions, route-level TTL
- **🛡️ Automatic invalidation** - cache invalidation for modifying requests
- **📊 Minimal overhead** - efficient handling of large numbers of routes


## 📄 License

MIT License - see [LICENSE](LICENSE)

---

⭐ **Like the project? Give it a star!**

🐛 **Found a bug?** [Create an issue](https://github.com/chud0/FastCacheMiddleware/issues)

💡 **Have an idea?** [Suggest a feature](https://github.com/chud0/FastCacheMiddleware/discussions/categories/ideas)