# FastCacheMiddleware

Интеллектуальный middleware для кеширования ответов FastAPI с поддержкой конфигурации через dependencies и автоматической инвалидации кеша.

## 🚀 Основные возможности

- **Конфигурация через dependencies**: Настройка кеширования непосредственно в роутах через систему зависимостей FastAPI
- **Автоматическая инвалидация**: Умная инвалидация кеша при модифицирующих запросах (POST, PUT, DELETE)
- **Гибкие ключи кеширования**: Настраиваемые функции генерации ключей на основе параметров запроса
- **Заголовки X-Cache**: Автоматическое добавление заголовков статуса кеша (HIT/MISS/BYPASS/EXPIRED)
- **Асинхронная работа**: Полная поддержка async/await для высокой производительности
- **Расширяемость**: Поддержка различных бэкендов хранения (Memory, Redis, и др.)

## 📦 Установка

```bash
pip install fast-cache-middleware
```

## 🔧 Быстрый старт

```python
from fastapi import Depends, FastAPI
from fast_cache_middleware import (
    CacheConfig, 
    CacheDropConfig, 
    CacheVisibility, 
    FastCacheMiddleware, 
    MemoryCacheStore
)
from fast_cache_middleware.middleware import cache_dependency, cache_drop_dependency

# Создание приложения
app = FastAPI()

# Добавление middleware
store = MemoryCacheStore()
app.add_middleware(FastCacheMiddleware, default_store=store)

# Конфигурация кеширования для GET-запросов
cache_config = CacheConfig(
    max_age=300,  # 5 минут
    visibility=CacheVisibility.PRIVATE,
    key_func=lambda r: f"data_{r.path_params['id']}"
)

# Конфигурация инвалидации для модифицирующих запросов
cache_drop_config = CacheDropConfig(
    paths=["/data/{id}"],
    key_template="data_{id}",
    on_methods=["POST", "PUT", "DELETE"]
)

# Роут с кешированием
@app.get("/data/{id}", dependencies=[Depends(cache_dependency(cache_config))])
async def get_data(id: str):
    # Этот ответ будет кеширован
    return {"id": id, "data": "some_data"}

# Роут с инвалидацией кеша
@app.post("/data/{id}", dependencies=[Depends(cache_drop_dependency(cache_drop_config))])
async def update_data(id: str, data: dict):
    # Этот запрос инвалидирует кеш для соответствующего GET-роута
    return {"id": id, "status": "updated"}
```

## 📋 Конфигурация

### CacheConfig

Класс для настройки параметров кеширования:

```python
CacheConfig(
    max_age: int,                           # Время жизни кеша в секундах
    visibility: CacheVisibility,            # PUBLIC или PRIVATE
    key_func: Callable[[Request], str],     # Функция генерации ключа
    cache_store: Optional[Type[AbstractCacheStore]] = None  # Тип хранилища
)
```

**Параметры:**
- `max_age`: Время жизни кеша в секундах
- `visibility`: Видимость кеша (PUBLIC/PRIVATE)
- `key_func`: Функция для генерации уникального ключа кеша на основе запроса
- `cache_store`: Тип хранилища кеша (опционально)

### CacheDropConfig

Класс для настройки инвалидации кеша:

```python
CacheDropConfig(
    paths: List[str],                       # Пути для инвалидации
    key_template: str,                      # Шаблон ключа для инвалидации
    on_methods: List[str] = ["POST", "PUT", "DELETE"]  # HTTP методы
)
```

**Параметры:**
- `paths`: Список путей в формате `/endpoint/{param}` для инвалидации
- `key_template`: Шаблон ключа для массовой инвалидации (например, `"data_{id}"`)
- `on_methods`: HTTP методы, которые триггерируют инвалидацию

## 🎯 Примеры использования

### Базовое кеширование

```python
# Простое кеширование на 5 минут
cache_config = CacheConfig(
    max_age=300,
    visibility=CacheVisibility.PUBLIC,
    key_func=lambda r: f"users_{r.path_params['user_id']}"
)

@app.get("/users/{user_id}", dependencies=[Depends(cache_dependency(cache_config))])
async def get_user(user_id: int):
    # Дорогая операция получения пользователя
    return await fetch_user_from_db(user_id)
```

### Кеширование с параметрами запроса

```python
# Кеширование с учетом query параметров
def search_key_func(request: Request) -> str:
    query = request.query_params.get("q", "")
    page = request.query_params.get("page", "1")
    return f"search_{query}_{page}"

search_cache_config = CacheConfig(
    max_age=600,  # 10 минут
    visibility=CacheVisibility.PUBLIC,
    key_func=search_key_func
)

@app.get("/search", dependencies=[Depends(cache_dependency(search_cache_config))])
async def search(q: str, page: int = 1):
    return await perform_search(q, page)
```

### Инвалидация кеша

```python
# Инвалидация при обновлении пользователя
user_drop_config = CacheDropConfig(
    paths=["/users/{user_id}", "/users"],  # Инвалидируем и конкретного пользователя, и список
    key_template="users_{user_id}",
    on_methods=["PUT", "DELETE"]
)

@app.put("/users/{user_id}", dependencies=[Depends(cache_drop_dependency(user_drop_config))])
async def update_user(user_id: int, user_data: dict):
    # Обновление пользователя инвалидирует его кеш
    return await update_user_in_db(user_id, user_data)
```

### Условное кеширование

```python
# Кеширование только для определенных условий
def conditional_key_func(request: Request) -> str:
    user_type = request.headers.get("X-User-Type", "guest")
    if user_type == "premium":
        return f"premium_data_{request.path_params['id']}"
    return f"regular_data_{request.path_params['id']}"

conditional_cache_config = CacheConfig(
    max_age=1800,  # 30 минут для премиум пользователей
    visibility=CacheVisibility.PRIVATE,
    key_func=conditional_key_func
)
```

## 🏗️ Архитектура

### Компоненты

1. **FastCacheMiddleware**: Основной middleware, обрабатывающий запросы
2. **CacheConfig/CacheDropConfig**: Классы конфигурации
3. **AbstractCacheStore**: Абстрактный интерфейс для хранилищ
4. **MemoryCacheStore**: Реализация in-memory хранилища
5. **Dependency функции**: Помощники для интеграции с FastAPI

### Поток выполнения

1. **Запрос поступает в middleware**
2. **Выполнение основного обработчика** (для получения конфигураций из dependencies)
3. **Извлечение конфигураций** из `request.state`
4. **Обработка кеширования** (для GET) или **инвалидации** (для POST/PUT/DELETE)
5. **Установка заголовков X-Cache**
6. **Возврат ответа**

### Заголовки X-Cache

Middleware автоматически добавляет заголовок `X-Cache` со следующими значениями:

- `HIT`: Ответ получен из кеша
- `MISS`: Кеш отсутствует, выполнен реальный запрос
- `EXPIRED`: Кеш истек, выполнен новый запрос
- `BYPASS`: Кеширование пропущено (например, из-за заголовков Cache-Control)

## 🔌 Расширение

### Создание собственного хранилища

```python
from fast_cache_middleware.stores import AbstractCacheStore

class RedisCacheStore(AbstractCacheStore):
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
    
    async def get(self, key: str) -> Optional[Dict]:
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    async def set(self, key: str, value: Dict, max_age: int) -> None:
        await self.redis.setex(key, max_age, json.dumps(value))
    
    async def delete_pattern(self, pattern: str) -> None:
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)
```

### Интеграция с библиотекой hishel

Для совместимости с популярной библиотекой кеширования:

```python
import hishel

# Использование протоколов hishel для совместимости
class HishelCompatibleStore(AbstractCacheStore):
    def __init__(self):
        self.storage = hishel.InMemoryStorage()
    
    # Реализация методов с использованием hishel API
```

## 🧪 Тестирование

Запуск демонстрации:

```bash
python test_cache.py
```

Запуск примера:

```bash
cd examples
python basic.py
```

## 📊 Производительность

- **Минимальные накладные расходы**: Middleware добавляет менее 1мс к времени ответа
- **Асинхронная работа**: Полная поддержка async/await
- **Параллельные запросы**: Безопасная работа в многопоточной среде
- **Эффективное хранение**: Оптимизированная сериализация данных

## 🔒 Безопасность

- **Изоляция кеша**: Поддержка PRIVATE/PUBLIC видимости
- **Валидация ключей**: Защита от cache poisoning
- **Контроль доступа**: Интеграция с системой аутентификации FastAPI

## 🤝 Совместимость

- **FastAPI**: 0.100+
- **Python**: 3.8+
- **Starlette**: 0.27+
- **Pydantic**: 2.0+

## 📝 Лицензия

MIT License

## 🛠️ Разработка

```bash
# Клонирование репозитория
git clone https://github.com/your-repo/fast-cache-middleware.git

# Установка зависимостей
poetry install

# Запуск тестов
pytest

# Запуск примеров
python examples/basic.py
```

## 📞 Поддержка

- **Issues**: [GitHub Issues](https://github.com/your-repo/fast-cache-middleware/issues)
- **Документация**: [Полная документация](https://fast-cache-middleware.readthedocs.io/)
- **Примеры**: [Больше примеров](https://github.com/your-repo/fast-cache-middleware/tree/main/examples)

---

**FastCacheMiddleware** - мощное и гибкое решение для кеширования в FastAPI приложениях! 🚀