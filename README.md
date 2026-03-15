# Shorten Links API

Сервис для сокращения ссылок на FastAPI + PostgreSQL + Redis.

Развернутый сервис на render.com [тут](https://shorten-links-z86x.onrender.com).

## Стек

- **FastAPI** - веб-фреймворк
- **PostgreSQL** - основное хранилище
- **Redis** - кэширование редиректов и статистики
- **SQLAlchemy** (async) - ORM
- **JWT** - аутентификация

## Запуск

### Через docker-compose

```bash
cp .env.example .env # поправить значения
docker-compose up --build
```

### Локально (нужны postgres и redis)

```bash
pip install -r requirements.txt
# поправить DATABASE_URL и REDIS_URL в .env на localhost
uvicorn app.main:app --reload
```

Swagger UI: `http://localhost:8000/docs`

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `DATABASE_URL` | строка подключения к postgres | — |
| `REDIS_URL` | строка подключения к redis | — |
| `SECRET_KEY` | секрет для JWT | — |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | время жизни токена (мин) | 60 |
| `UNUSED_LINK_DAYS` | дней до удаления неактивной ссылки | 30 |

## API

### Аутентификация

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| POST | `/auth/register` | регистрация | все |
| POST | `/auth/login` | получить JWT токен | все |
| GET | `/auth/me` | инфо о себе | авторизованные |

### Ссылки

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| POST | `/links/shorten` | создать короткую ссылку | все |
| GET | `/links/{short_code}` | редирект на оригинальный URL | все |
| DELETE | `/links/{short_code}` | удалить ссылку | только владелец |
| PUT | `/links/{short_code}` | обновить ссылку | только владелец |
| GET | `/links/{short_code}/stats` | статистика по ссылке | все |
| GET | `/links/search?original_url=` | поиск по оригинальному URL | все |
| GET | `/links/expired-history` | история истёкших/удалённых ссылок | все |
| DELETE | `/links/cleanup/unused` | удалить неиспользуемые ссылки | авторизованные |

### Примеры запросов

**Регистрация:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "ivan", "email": "ivan@example.com", "password": "secret"}'
```

**Логин:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -d "username=ivan&password=secret"
```

**Создать ссылку (с токеном):**
```bash
curl -X POST http://localhost:8000/links/shorten \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/very/long/url"}'
```

**Создать с кастомным alias и сроком жизни:**
```bash
curl -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com", "custom_alias": "mylink", "expires_at": "2026-12-31T23:59:00"}'
```

**Статистика:**
```bash
curl http://localhost:8000/links/mylink/stats
```

**Поиск:**
```bash
curl "http://localhost:8000/links/search?original_url=https://example.com/"
```

## Описание БД

**users** — пользователи
- `id`, `username`, `email`, `hashed_password`, `created_at`

**links** — активные ссылки
- `id`, `short_code` (уникальный), `original_url`, `user_id` (null если аноним), `created_at`, `last_used_at`, `use_count`, `expires_at`

**expired_links** — история истёкших/удалённых ссылок
- `id`, `short_code`, `original_url`, `user_id`, `created_at`, `expired_at`, `use_count`, `reason` (expired/deleted/unused)

## Кэширование

Redis кэширует:
- `link:{short_code}` — URL для редиректа, TTL 5 минут
- `stats:{short_code}` — статистика, TTL 60 секунд

Кэш инвалидируется при обновлении или удалении ссылки.

## Тестирование

### Запуск тестов

```bash
pip install -r requirements.txt
pytest tests/ -v
```

### Покрытие кода

```bash
coverage run -m pytest tests/
coverage report         # в терминале
coverage html           # HTML-отчёт в папке htmlcov/
```

Открыть отчёт: `htmlcov/index.html`

**Текущее покрытие: 92%** (требование: ≥ 90%)

### Структура тестов

| Файл | Описание |
|---|---|
| `tests/test_unit.py` | юнит-тесты: генерация кодов, хэширование паролей, JWT |
| `tests/test_auth.py` | функциональные тесты аутентификации (register, login, /me) |
| `tests/test_links.py` | функциональные тесты ссылок (CRUD, редирект, кэш, cleanup) |
| `tests/test_direct.py` | прямые вызовы async-функций для полного покрытия |
| `tests/locustfile.py` | нагрузочные тесты (Locust) |

Тесты используют SQLite in-memory вместо PostgreSQL и FakeRedis вместо реального Redis — внешние зависимости не нужны.

### Нагрузочное тестирование

```bash
# тест локально
uvicorn app.main:app --host 0.0.0.0 --port 8000 # в отдельном терминале
locust -f tests/locustfile.py --host http://localhost:8000

# тест задеплоенного сервиса
locust -f tests/locustfile.py --host https://shorten-links-z86x.onrender.com
```

Веб-интерфейс: `http://localhost:8089`

#### Результаты (50 пользователей, render.com)

| Эндпоинт | Median | Avg | RPS |
|---|---|---|---|
| `GET /links/{code}` (без кэша) | 660 ms | 797 ms | 4.8 |
| `GET /links/{code}` (кэш) | 600 ms | 743 ms | **17.8** |
| `GET /links/{code}/stats` (без кэша) | 470 ms | 572 ms | 2.0 |
| `GET /links/{code}/stats` (кэш) | 310 ms | 365 ms | **4.4** |

Кэширование даёт прирост пропускной способности в **3–4 раза** для повторных запросов. Ошибок: 0 из 8 377 запросов.
