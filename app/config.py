from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # настройки бд
    database_url: str
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "shortlinks"

    # редис
    redis_url: str = "redis://localhost:6379/0"

    # jwt
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # кол-во дней до удаления неиспользуемой ссылки
    unused_link_days: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
