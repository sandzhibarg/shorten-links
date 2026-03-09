from datetime import datetime
from pydantic import BaseModel, HttpUrl


# схемы для юзеров
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

# схемы для ссылок
class LinkCreate(BaseModel):
    original_url: HttpUrl
    custom_alias: str | None = None
    expires_at: datetime | None = None

class LinkUpdate(BaseModel):
    # можно обновить либо сам юрл либо short_code
    original_url: HttpUrl | None = None
    short_code: str | None = None

class LinkOut(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}

class LinkStats(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    last_used_at: datetime | None = None
    use_count: int
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}

class ExpiredLinkOut(BaseModel):
    short_code: str
    original_url: str
    user_id: int | None = None
    created_at: datetime
    expired_at: datetime
    use_count: int
    reason: str

    model_config = {"from_attributes": True}
