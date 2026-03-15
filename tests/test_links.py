from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.models import Link, User


class TestShortenLink:
    # тесты создания коротких ссылок

    async def test_shorten_anonymous(self, client):
        resp = await client.post("/links/shorten", json={
            "original_url": "https://www.wildberries.ru",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "short_code" in data
        assert len(data["short_code"]) == 8
        assert data["original_url"] == "https://www.wildberries.ru/"

    async def test_shorten_authenticated(self, client, test_user, auth_headers):
        resp = await client.post("/links/shorten", json={
            "original_url": "https://www.ozon.ru/category/elektronika/",
        }, headers=auth_headers)
        assert resp.status_code == 201
        assert "short_code" in resp.json()

    async def test_shorten_custom_alias(self, client):
        resp = await client.post("/links/shorten", json={
            "original_url": "https://www.avito.ru",
            "custom_alias": "mylink",
        })
        assert resp.status_code == 201
        assert resp.json()["short_code"] == "mylink"

    async def test_shorten_duplicate_alias(self, client):
        await client.post("/links/shorten", json={
            "original_url": "https://vk.com",
            "custom_alias": "dupealias",
        })
        resp = await client.post("/links/shorten", json={
            "original_url": "https://ok.ru",
            "custom_alias": "dupealias",
        })
        assert resp.status_code == 400

    async def test_shorten_with_expiry(self, client):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        resp = await client.post("/links/shorten", json={
            "original_url": "https://market.yandex.ru",
            "expires_at": future,
        })
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    async def test_shorten_invalid_url(self, client):
        resp = await client.post("/links/shorten", json={
            "original_url": "not-a-valid-url",
        })
        assert resp.status_code == 422

    async def test_shorten_missing_url(self, client):
        resp = await client.post("/links/shorten", json={})
        assert resp.status_code == 422

    async def test_shorten_multiple_times_same_url(self, client):
        # одну и ту же ссылку можно сократить несколько раз
        r1 = await client.post("/links/shorten", json={"original_url": "https://www.wildberries.ru"})
        r2 = await client.post("/links/shorten", json={"original_url": "https://www.wildberries.ru"})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["short_code"] != r2.json()["short_code"]

class TestRedirect:
    # тесты редиректа

    async def test_redirect_success(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.ozon.ru",
        })
        code = create_resp.json()["short_code"]

        resp = await client.get(f"/links/{code}", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://www.ozon.ru/"

    async def test_redirect_not_found(self, client):
        resp = await client.get("/links/doesnotexist123", follow_redirects=False)
        assert resp.status_code == 404

    async def test_redirect_increments_use_count(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.avito.ru",
        })
        code = create_resp.json()["short_code"]

        await client.get(f"/links/{code}", follow_redirects=False)
        await client.get(f"/links/{code}", follow_redirects=False)

        stats = await client.get(f"/links/{code}/stats")
        assert stats.json()["use_count"] == 2

    async def test_redirect_expired_link(self, client, db_session):
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        link = Link(
            short_code="expiredlink",
            original_url="https://vk.com",
            expires_at=past,
        )
        db_session.add(link)
        await db_session.commit()

        resp = await client.get("/links/expiredlink", follow_redirects=False)
        assert resp.status_code == 410

    async def test_redirect_expired_moves_to_history(self, client, db_session):
        # истекшая ссылка при обращении должна попасть в историю
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        link = Link(
            short_code="expiredmove",
            original_url="https://ok.ru",
            expires_at=past,
        )
        db_session.add(link)
        await db_session.commit()

        await client.get("/links/expiredmove", follow_redirects=False)

        hist = await client.get("/links/expired-history")
        codes = [e["short_code"] for e in hist.json()]
        assert "expiredmove" in codes

    async def test_redirect_uses_cache_on_second_request(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://market.yandex.ru",
        })
        code = create_resp.json()["short_code"]

        # первый запрос - кэшируется
        r1 = await client.get(f"/links/{code}", follow_redirects=False)
        # второй - из кэша
        r2 = await client.get(f"/links/{code}", follow_redirects=False)

        assert r1.status_code == 307
        assert r2.status_code == 307
        assert r1.headers["location"] == r2.headers["location"]

class TestGetStats:
    # тесты статистики ссылки

    async def test_get_stats_success(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.wildberries.ru",
        })
        code = create_resp.json()["short_code"]

        resp = await client.get(f"/links/{code}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["short_code"] == code
        assert data["use_count"] == 0
        assert data["original_url"] == "https://www.wildberries.ru/"
        assert "created_at" in data

    async def test_get_stats_not_found(self, client):
        resp = await client.get("/links/nonexistent999/stats")
        assert resp.status_code == 404

    async def test_stats_use_count_after_redirect(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.lamoda.ru",
        })
        code = create_resp.json()["short_code"]

        await client.get(f"/links/{code}", follow_redirects=False)

        stats = await client.get(f"/links/{code}/stats")
        assert stats.json()["use_count"] == 1

    async def test_stats_cached_on_second_call(self, client):
        # повторный запрос статистики отдается из кэша
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.dns-shop.ru",
        })
        code = create_resp.json()["short_code"]

        r1 = await client.get(f"/links/{code}/stats")
        r2 = await client.get(f"/links/{code}/stats")
        # данные одинаковые - значит кэш работает
        assert r1.json()["short_code"] == r2.json()["short_code"]
        assert r1.json()["use_count"] == r2.json()["use_count"]

class TestDeleteLink:
    # тесты удаления ссылок

    async def test_delete_success(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.ozon.ru",
        }, headers=auth_headers)
        code = create_resp.json()["short_code"]

        del_resp = await client.delete(f"/links/{code}", headers=auth_headers)
        assert del_resp.status_code == 204

    async def test_delete_link_no_longer_accessible(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.avito.ru",
        }, headers=auth_headers)
        code = create_resp.json()["short_code"]

        await client.delete(f"/links/{code}", headers=auth_headers)

        redir = await client.get(f"/links/{code}", follow_redirects=False)
        assert redir.status_code == 404

    async def test_delete_unauthenticated(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://vk.com",
        })
        code = create_resp.json()["short_code"]

        resp = await client.delete(f"/links/{code}")
        assert resp.status_code == 401

    async def test_delete_not_owner(self, client, db_session, test_user, auth_headers):
        # создаем другого юзера и его ссылку
        other = User(
            username="otheruser",
            email="other@example.com",
            hashed_password=hash_password("pass"),
        )
        db_session.add(other)
        await db_session.commit()
        await db_session.refresh(other)

        link = Link(
            short_code="notmylink",
            original_url="https://www.wildberries.ru/",
            user_id=other.id,
        )
        db_session.add(link)
        await db_session.commit()

        resp = await client.delete("/links/notmylink", headers=auth_headers)
        assert resp.status_code == 403

    async def test_delete_not_found(self, client, test_user, auth_headers):
        resp = await client.delete("/links/nosuchlink", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_moves_to_expired_history(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://ok.ru",
        }, headers=auth_headers)
        code = create_resp.json()["short_code"]

        await client.delete(f"/links/{code}", headers=auth_headers)

        hist = await client.get("/links/expired-history")
        codes = [e["short_code"] for e in hist.json()]
        assert code in codes

    async def test_deleted_link_reason_is_deleted(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://market.yandex.ru",
        }, headers=auth_headers)
        code = create_resp.json()["short_code"]

        await client.delete(f"/links/{code}", headers=auth_headers)

        hist = await client.get("/links/expired-history")
        entry = next(e for e in hist.json() if e["short_code"] == code)
        assert entry["reason"] == "deleted"

class TestUpdateLink:
    # тесты обновления ссылок

    async def test_update_original_url(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.wildberries.ru",
        }, headers=auth_headers)
        code = create_resp.json()["short_code"]

        upd = await client.put(f"/links/{code}", json={
            "original_url": "https://www.ozon.ru",
        }, headers=auth_headers)
        assert upd.status_code == 200
        assert upd.json()["original_url"] == "https://www.ozon.ru/"

    async def test_update_short_code(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.avito.ru",
        }, headers=auth_headers)
        old_code = create_resp.json()["short_code"]

        upd = await client.put(f"/links/{old_code}", json={
            "short_code": "newcustomcode",
        }, headers=auth_headers)
        assert upd.status_code == 200
        assert upd.json()["short_code"] == "newcustomcode"

    async def test_update_old_code_stops_working(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://vk.com",
        }, headers=auth_headers)
        old_code = create_resp.json()["short_code"]

        await client.put(f"/links/{old_code}", json={
            "short_code": "freshcode123",
        }, headers=auth_headers)

        resp = await client.get(f"/links/{old_code}", follow_redirects=False)
        assert resp.status_code == 404

    async def test_update_new_code_works(self, client, test_user, auth_headers):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.dns-shop.ru",
        }, headers=auth_headers)
        old_code = create_resp.json()["short_code"]

        await client.put(f"/links/{old_code}", json={
            "short_code": "workingcode",
        }, headers=auth_headers)

        resp = await client.get("/links/workingcode", follow_redirects=False)
        assert resp.status_code == 307

    async def test_update_unauthenticated(self, client):
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.wildberries.ru",
        })
        code = create_resp.json()["short_code"]

        resp = await client.put(f"/links/{code}", json={
            "original_url": "https://www.ozon.ru",
        })
        assert resp.status_code == 401

    async def test_update_not_owner(self, client, db_session, test_user, auth_headers):
        other = User(
            username="otheruser2",
            email="other2@example.com",
            hashed_password=hash_password("pass"),
        )
        db_session.add(other)
        await db_session.commit()
        await db_session.refresh(other)

        link = Link(
            short_code="otherlink",
            original_url="https://www.avito.ru/",
            user_id=other.id,
        )
        db_session.add(link)
        await db_session.commit()

        resp = await client.put("/links/otherlink", json={
            "original_url": "https://vk.com",
        }, headers=auth_headers)
        assert resp.status_code == 403

    async def test_update_duplicate_short_code(self, client, test_user, auth_headers):
        r1 = await client.post("/links/shorten", json={"original_url": "https://vk.com"}, headers=auth_headers)
        r2 = await client.post("/links/shorten", json={"original_url": "https://ok.ru"}, headers=auth_headers)
        code1 = r1.json()["short_code"]
        code2 = r2.json()["short_code"]

        # пытаемся переименовать в уже существующий код
        resp = await client.put(f"/links/{code1}", json={"short_code": code2}, headers=auth_headers)
        assert resp.status_code == 400

    async def test_update_not_found(self, client, test_user, auth_headers):
        resp = await client.put("/links/nosuchcode", json={
            "original_url": "https://www.wildberries.ru",
        }, headers=auth_headers)
        assert resp.status_code == 404

class TestSearch:
    # тесты поиска ссылок по оригинальному урлу

    async def test_search_found(self, client):
        await client.post("/links/shorten", json={"original_url": "https://www.wildberries.ru"})
        await client.post("/links/shorten", json={"original_url": "https://www.wildberries.ru"})

        resp = await client.get("/links/search", params={"original_url": "https://www.wildberries.ru/"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_search_not_found(self, client):
        resp = await client.get("/links/search", params={"original_url": "https://www.ozon.ru/"})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_returns_correct_fields(self, client):
        await client.post("/links/shorten", json={"original_url": "https://market.yandex.ru"})
        resp = await client.get("/links/search", params={"original_url": "https://market.yandex.ru/"})
        assert resp.status_code == 200
        item = resp.json()[0]
        assert "short_code" in item
        assert "original_url" in item
        assert "created_at" in item

class TestExpiredHistory:
    # тесты истории истекших ссылок

    async def test_history_empty_at_start(self, client):
        resp = await client.get("/links/expired-history")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_history_after_expired_access(self, client, db_session):
        past = datetime.now(timezone.utc) - timedelta(hours=3)
        link = Link(
            short_code="histexpired",
            original_url="https://vk.com/",
            expires_at=past,
        )
        db_session.add(link)
        await db_session.commit()

        await client.get("/links/histexpired", follow_redirects=False)

        resp = await client.get("/links/expired-history")
        codes = [e["short_code"] for e in resp.json()]
        assert "histexpired" in codes

    async def test_history_reason_field(self, client, db_session):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        link = Link(
            short_code="reasoncheck",
            original_url="https://ok.ru/",
            expires_at=past,
        )
        db_session.add(link)
        await db_session.commit()

        await client.get("/links/reasoncheck", follow_redirects=False)

        resp = await client.get("/links/expired-history")
        entry = next(e for e in resp.json() if e["short_code"] == "reasoncheck")
        assert entry["reason"] == "expired"

class TestCleanupUnused:
    # тесты очистки неиспользуемых ссылок

    async def test_cleanup_requires_auth(self, client):
        resp = await client.delete("/links/cleanup/unused")
        assert resp.status_code == 401

    async def test_cleanup_no_old_links(self, client, test_user, auth_headers):
        # нет старых ссылок - удаляет 0
        resp = await client.delete("/links/cleanup/unused", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0

    async def test_cleanup_removes_old_link(self, client, db_session, test_user, auth_headers):
        # создаем ссылку с очень старой датой создания
        old_time = datetime(2020, 1, 1)
        link = Link(
            short_code="veryoldlink",
            original_url="https://www.wildberries.ru/",
            created_at=old_time,
        )
        db_session.add(link)
        await db_session.commit()

        resp = await client.delete("/links/cleanup/unused", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1

        # ссылка удалена
        redir = await client.get("/links/veryoldlink", follow_redirects=False)
        assert redir.status_code == 404

    async def test_cleanup_keeps_fresh_links(self, client, test_user, auth_headers):
        # свежая ссылка не должна удалиться
        create_resp = await client.post("/links/shorten", json={
            "original_url": "https://www.ozon.ru",
        }, headers=auth_headers)
        code = create_resp.json()["short_code"]

        await client.delete("/links/cleanup/unused", headers=auth_headers)

        redir = await client.get(f"/links/{code}", follow_redirects=False)
        assert redir.status_code == 307

    async def test_cleanup_old_link_moves_to_history(self, client, db_session, test_user, auth_headers):
        old_time = datetime(2019, 6, 15)
        link = Link(
            short_code="oldhistlink",
            original_url="https://vk.com/",
            created_at=old_time,
        )
        db_session.add(link)
        await db_session.commit()

        await client.delete("/links/cleanup/unused", headers=auth_headers)

        hist = await client.get("/links/expired-history")
        codes = [e["short_code"] for e in hist.json()]
        assert "oldhistlink" in codes
