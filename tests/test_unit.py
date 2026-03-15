import re
from datetime import datetime, timezone

import pytest
from jose import jwt

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.routers.links import generate_short_code


class TestGenerateShortCode:
    # тесты для функции генерации коротких кодов

    def test_default_length(self):
        code = generate_short_code()
        assert len(code) == 8

    def test_custom_length(self):
        code = generate_short_code(12)
        assert len(code) == 12

    def test_small_length(self):
        code = generate_short_code(4)
        assert len(code) == 4

    def test_only_urlsafe_chars(self):
        # в коде должны быть только url-безопасные символы
        for _ in range(50):
            code = generate_short_code()
            assert re.match(r"^[A-Za-z0-9_-]+$", code), f"невалидный символ в коде: {code}"

    def test_uniqueness(self):
        # 200 кодов подряд - статистически все должны различатся
        codes = [generate_short_code() for _ in range(200)]
        assert len(set(codes)) > 190

    def test_returns_string(self):
        assert isinstance(generate_short_code(), str)

class TestHashPassword:
    # тесты хэширования паролей

    def test_hash_not_equal_to_plain(self):
        plain = "supersecret"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_hash_is_string(self):
        assert isinstance(hash_password("somepass"), str)

    def test_same_password_gives_different_hashes(self):
        # bcrypt использует соль - каждый раз разный хэш
        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert h1 != h2

    def test_hash_looks_like_bcrypt(self):
        # bcrypt хэши начинаются с $2b$
        hashed = hash_password("testpass")
        assert hashed.startswith("$2b$")

class TestVerifyPassword:
    # тесты проверки пароля

    def test_correct_password_returns_true(self):
        plain = "mypassword123"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("correctpass")
        assert verify_password("wrongpass", hashed) is False

    def test_empty_password_wrong(self):
        hashed = hash_password("notempty")
        assert verify_password("", hashed) is False

    def test_similar_password_wrong(self):
        # пароль с пробелом в конце - другой пароль
        hashed = hash_password("password")
        assert verify_password("password ", hashed) is False

class TestCreateAccessToken:
    # тесты создания jwt токенов

    def test_returns_string(self):
        token = create_access_token({"sub": "testuser"})
        assert isinstance(token, str)

    def test_token_contains_sub(self):
        token = create_access_token({"sub": "ivan_petrov"})
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["sub"] == "ivan_petrov"

    def test_token_has_expiry_field(self):
        token = create_access_token({"sub": "testuser"})
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert "exp" in payload

    def test_token_expires_in_future(self):
        token = create_access_token({"sub": "testuser"})
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)

    def test_token_not_decodable_with_wrong_key(self):
        from jose import JWTError

        token = create_access_token({"sub": "testuser"})
        with pytest.raises(JWTError):
            jwt.decode(token, "wrong-secret-key", algorithms=[settings.algorithm])

    def test_extra_data_preserved(self):
        # доп поля в токене должны сохраниться
        token = create_access_token({"sub": "user", "role": "admin"})
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["role"] == "admin"
