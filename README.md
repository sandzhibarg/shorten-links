# Shorten Links API

Сервис для сокращения ссылок на FastAPI + PostgreSQL + Redis.

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
