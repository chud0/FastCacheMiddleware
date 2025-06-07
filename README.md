# FastCacheMiddleware

Интеллектуальное middleware для кеширования ответов FastAPI с гибкой настройкой и автоматической инвалидацией.

## Возможности

- 🎯 Определение параметров кеширования через dependencies в роутах
- 🔄 Автоматическая инвалидация кеша при модифицирующих запросах
- ⚙️ Гибкая настройка ключей кеширования и правил инвалидации
- 🚀 Асинхронная работа с различными бэкендами кеширования
- 📊 Поддержка метрик и мониторинга (в разработке)
- 🔒 Управление видимостью кеша (PUBLIC/PRIVATE)

## Установка

```bash
poetry add fast-cache-middleware
```

## Быстрый старт

```python
from fastapi import FastAPI, Depends
from fast_cache_middleware import CacheConfig, CacheDropConfig, CacheVisibility

app = FastAPI()

@app.get(
    "/data/{id}",
    dependencies=[
        Depends(CacheConfig(
            max_age=300,
            visibility=CacheVisibility.PRIVATE,
            key_func=lambda r: f"data_{r.path_params['id']}"
        ))
    ]
)
async def get_data(id: str):
    return {"id": id, "data": "some_data"}

@app.post(
    "/data/{id}",
    dependencies=[
        Depends(CacheDropConfig(
            paths=["/data/{id}"],
            key_template="data_{id}"
        ))
    ]
)
async def update_data(id: str):
    return {"id": id, "status": "updated"}
```

## Структура проекта

```
fast_cache_middleware/
├── __init__.py
├── config.py          # Конфигурационные классы
├── middleware.py      # Основной middleware
├── route.py           # Кастомный APIRoute
├── types.py           # Типы и протоколы
├── stores/
│   ├── __init__.py
│   ├── base.py        # Базовый класс хранилища
│   └── memory.py      # In-memory хранилище
├── utils/
│   ├── __init__.py
│   ├── key_generator.py  # Генераторы ключей
│   └── validators.py     # Валидаторы
├── examples/
│   ├── __init__.py
│   ├── basic.py          # Базовый пример
│   ├── advanced.py       # Продвинутый пример
│   └── custom_store.py   # Пример кастомного хранилища
└── tests/
    ├── __init__.py
    ├── test_middleware.py
    ├── test_stores.py
    └── test_utils.py
```

## Основные компоненты

### Конфигурация (config.py)

- `CacheConfig` - конфигурация кеширования для GET-запросов
- `CacheDropConfig` - конфигурация инвалидации для модифицирующих запросов
- `CacheVisibility` - enum для управления видимостью кеша

### Middleware (middleware.py)

- `FastCacheMiddleware` - основной middleware для обработки кеширования
- Интеграция с FastAPI через кастомный `APIRoute`
- Обработка зависимостей и конфигураций
- Управление жизненным циклом кеша

### Хранилища (stores/)

- `BaseCacheStore` - протокол для реализации хранилищ
- `MemoryCacheStore` - in-memory реализация

### Утилиты (types.py и др.)

- Генераторы ключей кеширования
- Валидаторы конфигурации
- Вспомогательные функции

## Примеры использования

Подробные примеры доступны в директории `examples/`:

- `basic.py` - базовое использование middleware
- `