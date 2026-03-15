import pytest


class TestRegister:
    # тесты регистрации пользователя

    async def test_register_success(self, client):
        resp = await client.post("/auth/register", json={
            "username": "noviy_user",
            "email": "noviy@example.com",
            "password": "pass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "noviy_user"
        assert data["email"] == "noviy@example.com"
        assert "id" in data
        assert "created_at" in data

    async def test_register_response_no_password(self, client):
        # пароль не должен возвращаться в ответе
        resp = await client.post("/auth/register", json={
            "username": "someuser",
            "email": "some@example.com",
            "password": "secretpass",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "password" not in data
        assert "hashed_password" not in data

    async def test_register_duplicate_username(self, client, test_user):
        resp = await client.post("/auth/register", json={
            "username": "testuser",  # уже занято
            "email": "other@example.com",
            "password": "pass123",
        })
        assert resp.status_code == 400

    async def test_register_duplicate_email(self, client, test_user):
        resp = await client.post("/auth/register", json={
            "username": "otherusr",
            "email": "test@example.com",  # уже занято
            "password": "pass123",
        })
        assert resp.status_code == 400

    async def test_register_missing_fields(self, client):
        # нет обязательных полей
        resp = await client.post("/auth/register", json={
            "username": "someuser",
        })
        assert resp.status_code == 422

    async def test_register_two_users(self, client):
        # два разных юзера регаются без проблем
        r1 = await client.post("/auth/register", json={
            "username": "user_one",
            "email": "one@example.com",
            "password": "pass1",
        })
        r2 = await client.post("/auth/register", json={
            "username": "user_two",
            "email": "two@example.com",
            "password": "pass2",
        })
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]

class TestLogin:
    # тесты логина

    async def test_login_success(self, client, test_user):
        resp = await client.post("/auth/login", data={
            "username": "testuser",
            "password": "testpass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_token_is_string(self, client, test_user):
        resp = await client.post("/auth/login", data={
            "username": "testuser",
            "password": "testpass123",
        })
        assert isinstance(resp.json()["access_token"], str)
        assert len(resp.json()["access_token"]) > 20

    async def test_login_wrong_password(self, client, test_user):
        resp = await client.post("/auth/login", data={
            "username": "testuser",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client):
        resp = await client.post("/auth/login", data={
            "username": "nosuchuser",
            "password": "somepass",
        })
        assert resp.status_code == 401

    async def test_login_empty_password(self, client, test_user):
        resp = await client.post("/auth/login", data={
            "username": "testuser",
            "password": "",
        })
        assert resp.status_code == 401

    async def test_login_wrong_returns_www_authenticate_header(self, client, test_user):
        # при 401 должен быть WWW-Authenticate заголовок
        resp = await client.post("/auth/login", data={
            "username": "testuser",
            "password": "badpass",
        })
        assert resp.status_code == 401
        assert "www-authenticate" in resp.headers

class TestGetMe:
    # тесты эндпоинта /auth/me

    async def test_get_me_success(self, client, test_user, auth_headers):
        resp = await client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"

    async def test_get_me_no_token(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token(self, client):
        resp = await client.get("/auth/me", headers={
            "Authorization": "Bearer this.is.not.valid",
        })
        assert resp.status_code == 401

    async def test_get_me_malformed_header(self, client):
        # заголовок без Bearer
        resp = await client.get("/auth/me", headers={
            "Authorization": "Basic sometoken",
        })
        assert resp.status_code == 401

    async def test_get_me_after_register_and_login(self, client):
        # полный флоу: регистрация > логин > /me
        await client.post("/auth/register", json={
            "username": "fullflow",
            "email": "flow@example.com",
            "password": "flowpass",
        })
        login_resp = await client.post("/auth/login", data={
            "username": "fullflow",
            "password": "flowpass",
        })
        token = login_resp.json()["access_token"]

        me_resp = await client.get("/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "fullflow"
