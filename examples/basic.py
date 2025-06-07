"""
Базовый пример использования FastCacheMiddleware.

Этот пример демонстрирует базовое использование middleware
для кеширования ответов API.
"""
from fastapi import Depends, FastAPI, Request
from fast_cache_middleware import CacheConfig, CacheDropConfig, CacheVisibility, FastCacheMiddleware, MemoryCacheStore
import logging

logger = logging.getLogger(__name__)

# Функция, возвращающая конфигурацию кеширования для GET-запросов (получение сущности)
def get_cache_config() -> CacheConfig:
    return CacheConfig(max_age=300, visibility=CacheVisibility.PRIVATE, key_func=lambda r: f"data_{r.path_params['id']}")

# Функция, возвращающая конфигурацию инвалидации (drop) для POST-запросов (создание сущности)
def get_cache_drop_config() -> CacheDropConfig:
    return CacheDropConfig(paths=["/data/{id}"], key_template="data_{id}")

# Создание экземпляра FastAPI
app = FastAPI()

# Инициализация хранилища (in-memory) и middleware
store = MemoryCacheStore()

app.add_middleware(FastCacheMiddleware, default_store=store)

# Базовый GET-роут (получение сущности) с кешированием
@app.get("/data/{id}", dependencies=[Depends(get_cache_config)])
async def get_data(id: str, request: Request):
    logger.info("get_data: %s", id)
    return {"id": id, "data": "some_data"}

# Базовый POST-роут (создание сущности) с инвалидацией (drop) кеша
@app.post("/data/{id}", dependencies=[Depends(get_cache_drop_config)])
async def update_data(id: str, request: Request):
    logger.info("update_data: %s", id)
    print("3" * 200)
    return {"id": id, "status": "updated"}

# Запуск приложения (например, через uvicorn) можно выполнить отдельно, например:
# uvicorn examples.basic:app --reload
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.DEBUG)


    uvicorn.run(
        "basic:app",
        host="127.0.0.1",
        port=8000,
    ) 