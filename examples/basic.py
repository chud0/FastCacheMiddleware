"""
Базовый пример использования FastCacheMiddleware
для кеширования ответов API.
"""
import logging
from fastapi import Depends, FastAPI, Request
from fast_cache_middleware import CacheConfig, CacheDropConfig, CacheVisibility, FastCacheMiddleware, MemoryCacheStore
from fast_cache_middleware.middleware import cache_dependency, cache_drop_dependency

# Настроим логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание экземпляра FastAPI
app = FastAPI()

# Инициализация хранилища (in-memory) и middleware
store = MemoryCacheStore()
app.add_middleware(FastCacheMiddleware, default_store=store)

# Конфигурация кеширования для GET-запроса (получение сущности)
cache_config = CacheConfig(
    max_age=300, 
    visibility=CacheVisibility.PRIVATE, 
    key_func=lambda r: f"data_{r.path_params['id']}"
)

# Конфигурация инвалидации для POST-запроса (создание сущности)
cache_drop_config = CacheDropConfig(
    paths=["/data/{id}"], 
    key_template="data_{id}"
)

# Базовый GET-роут (получение сущности) с кешированием
@app.get("/data/{id}", dependencies=[Depends(cache_dependency(cache_config))])
async def get_data(id: str, request: Request):
    logger.info(f"get_data: {id}")
    return {"id": id, "data": "some_data"}

# Базовый POST-роут (создание сущности) с инвалидацией (drop) кеша
@app.post("/data/{id}", dependencies=[Depends(cache_drop_dependency(cache_drop_config))])
async def update_data(id: str, request: Request):
    logger.info(f"update_data: {id}")
    return {"id": id, "status": "updated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000) 