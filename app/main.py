from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.cache import close_redis, init_redis
from app.database import Base, engine
import app.models  # noqa: F401 - нужен чтоб модели зарегались в Base.metadata


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover
    # инициализируем редис и создаем таблицы при старте
    await init_redis()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()

app = FastAPI(
    title="url shortener",
    description="сервис для сокращения ссылок",
    version="0.1.0",
    lifespan=lifespan,
)

from app.routers import auth, links

app.include_router(auth.router)
app.include_router(links.router)

@app.get("/")
async def root():
    return {"message": "url shortener api is running"}
