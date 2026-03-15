import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

import app.cache as cache_module
from app.auth import create_access_token, get_current_user, get_user_by_username, hash_password
from app.cache import get_redis
from app.main import root
from app.models import User
from app.routers.auth import login, register
from app.schemas import UserCreate


class TestGetUserByUsername:

    async def test_found(self, db_session):
        user = User(
            username="findme",
            email="findme@test.com",
            hashed_password=hash_password("pass"),
        )
        db_session.add(user)
        await db_session.commit()

        result = await get_user_by_username(db_session, "findme")
        assert result is not None
        assert result.username == "findme"

    async def test_not_found(self, db_session):
        result = await get_user_by_username(db_session, "nosuchuser")
        assert result is None

class TestGetCurrentUser:

    async def test_valid_token_returns_user(self, db_session, test_user):
        # токен с sub должен вернуть юзера
        token = create_access_token({"sub": test_user.username})
        result = await get_current_user(token, db_session)
        assert result is not None
        assert result.username == test_user.username

    async def test_token_without_sub_returns_none(self, db_session):
        # токен без поля sub должен вернуть None
        token = create_access_token({"role": "admin"})
        result = await get_current_user(token, db_session)
        assert result is None

class TestRegisterDirect:

    async def test_success(self, db_session):
        user_data = UserCreate(username="diruser1", email="dir1@test.com", password="pass")
        result = await register(user_data, db_session)
        assert result.username == "diruser1"
        assert result.email == "dir1@test.com"
        assert result.id is not None

    async def test_duplicate_raises_400(self, db_session):
        user_data = UserCreate(username="dupdir", email="dupdir@test.com", password="pass")
        await register(user_data, db_session)

        with pytest.raises(HTTPException) as exc:
            await register(user_data, db_session)
        assert exc.value.status_code == 400

class TestLoginDirect:

    async def test_success(self, db_session):
        user = User(
            username="logindir",
            email="logindir@test.com",
            hashed_password=hash_password("mysecret"),
        )
        db_session.add(user)
        await db_session.commit()

        form = OAuth2PasswordRequestForm(username="logindir", password="mysecret")
        result = await login(form, db_session)
        assert "access_token" in result
        assert result["token_type"] == "bearer"

    async def test_wrong_password_raises_401(self, db_session, test_user):
        form = OAuth2PasswordRequestForm(username="testuser", password="wrongpass")
        with pytest.raises(HTTPException) as exc:
            await login(form, db_session)
        assert exc.value.status_code == 401

    async def test_nonexistent_user_raises_401(self, db_session):
        form = OAuth2PasswordRequestForm(username="nouser", password="anypass")
        with pytest.raises(HTTPException) as exc:
            await login(form, db_session)
        assert exc.value.status_code == 401

class TestGetRedis:

    async def test_returns_fake_redis(self):
        # setup_and_clean_db (autouse) уже выставил fake redis
        result = await get_redis()
        assert result is not None

class TestRootEndpoint:

    async def test_returns_running_message(self):
        result = await root()
        assert "message" in result
        assert "running" in result["message"]
