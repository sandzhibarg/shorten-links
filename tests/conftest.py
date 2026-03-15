import os

# тестовые env-переменные до импорта приложения,
# чтобы pydantic-settings не прочитал реальный .env и упал
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.cache as cache_module
from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# создаем отдельный движок для тестов с in-memory sqlite
test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class FakeRedis:
    # простой фейк редиса чтоб не поднимать реальный
    def __init__(self):
        self._store = {}

    async def setex(self, key, ttl, value):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)

    async def aclose(self):
        pass


_fake_redis = FakeRedis()


@pytest.fixture(autouse=True)
async def setup_and_clean_db():
    # создаем таблицы перед каждым тестом (idempotent)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # подставляем фейковый редис вместо реального
    cache_module.redis_client = _fake_redis
    yield
    # после теста - чистим данные и сбрасываем кэш
    cache_module.redis_client = None
    _fake_redis._store.clear()
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client(db_session):
    # переопределяем get_db чтоб использовать тестовую sqlite
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session):
    # создаем тестового юзера напрямую в бд
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    # создаем валидный токен для тестового юзера
    token = create_access_token({"sub": test_user.username})
    return {"Authorization": f"Bearer {token}"}
