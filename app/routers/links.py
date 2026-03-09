import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_auth
from app.cache import cache_delete, cache_get, cache_set
from app.config import settings
from app.database import get_db
from app.models import ExpiredLink, Link, User
from app.schemas import ExpiredLinkOut, LinkCreate, LinkOut, LinkStats, LinkUpdate

router = APIRouter(prefix="/links", tags=["links"])

# ttl для кэша редиректа 5 мин
REDIRECT_CACHE_TTL = 300
# ttl для кэша статистики 60с
STATS_CACHE_TTL = 60


def generate_short_code(length: int = 8) -> str:
    # генерим случайный короткий код
    return secrets.token_urlsafe(length)[:length]

async def get_link_or_404(short_code: str, db: AsyncSession) -> Link:
    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="link not found")
    return link

async def invalidate_link_cache(short_code: str):
    # чистим все кэши по этой ссылке
    await cache_delete(f"link:{short_code}")
    await cache_delete(f"stats:{short_code}")

@router.post("/shorten", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def shorten_link(
    data: LinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    # создаем короткую ссылку, доступно всем
    original_url = str(data.original_url)

    if data.custom_alias:
        # проверяем уникальность alias
        existing = await db.execute(select(Link).where(Link.short_code == data.custom_alias))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="this alias is already taken",
            )
        short_code = data.custom_alias
    else:
        # генерим уникальный код
        for _ in range(5):
            short_code = generate_short_code()
            existing = await db.execute(select(Link).where(Link.short_code == short_code))
            if not existing.scalar_one_or_none():
                break
        else:
            raise HTTPException(status_code=500, detail="failed to generate unique code")

    link = Link(
        short_code=short_code,
        original_url=original_url,
        user_id=current_user.id if current_user else None,
        expires_at=data.expires_at,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link

@router.get("/search", response_model=list[LinkOut])
async def search_by_url(
    original_url: str,
    db: AsyncSession = Depends(get_db),
):
    # поиск всех коротких ссылок по оригинальному урлу
    result = await db.execute(select(Link).where(Link.original_url == original_url))
    links = result.scalars().all()
    return links

@router.get("/expired-history", response_model=list[ExpiredLinkOut])
async def get_expired_history(db: AsyncSession = Depends(get_db)):
    # история всех истекших и удаленых ссылок
    result = await db.execute(select(ExpiredLink).order_by(ExpiredLink.expired_at.desc()))
    return result.scalars().all()


@router.delete("/cleanup/unused", status_code=status.HTTP_200_OK)
async def cleanup_unused_links(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    # удаляем ссылки которые не использовались n дней (из конфига)
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.unused_link_days)

    result = await db.execute(
        select(Link).where(
            (Link.last_used_at < cutoff) | (Link.last_used_at.is_(None) & (Link.created_at < cutoff))
        )
    )
    unused = result.scalars().all()

    count = 0
    for link in unused:
        expired = ExpiredLink(
            short_code=link.short_code,
            original_url=link.original_url,
            user_id=link.user_id,
            created_at=link.created_at,
            use_count=link.use_count,
            reason="unused",
        )
        db.add(expired)
        await db.delete(link)
        await cache_delete(f"link:{link.short_code}")
        await cache_delete(f"stats:{link.short_code}")
        count += 1

    await db.commit()
    return {"deleted": count, "message": f"removed {count} unused links (inactive for {settings.unused_link_days} days)"}

@router.get("/{short_code}/stats", response_model=LinkStats)
async def get_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
):
    # статистика - сначала смотрим кэш
    cached = await cache_get(f"stats:{short_code}")
    if cached:
        return cached

    link = await get_link_or_404(short_code, db)

    stats_data = {
        "short_code": link.short_code,
        "original_url": link.original_url,
        "created_at": link.created_at.isoformat(),
        "last_used_at": link.last_used_at.isoformat() if link.last_used_at else None,
        "use_count": link.use_count,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }
    await cache_set(f"stats:{short_code}", stats_data, ttl=STATS_CACHE_TTL)
    return link

@router.get("/{short_code}")
async def redirect_to_url(
    short_code: str,
    db: AsyncSession = Depends(get_db),
):
    # редирект - сначала проверяем кэш чтоб не лезть в бд
    cached = await cache_get(f"link:{short_code}")
    if cached:
        # ссылка в кэше - обновляем счетчик в бд и редиректим
        result = await db.execute(select(Link).where(Link.short_code == short_code))
        link = result.scalar_one_or_none()
        if link:
            link.use_count += 1
            link.last_used_at = datetime.now(timezone.utc)
            await db.commit()
        return RedirectResponse(url=cached["original_url"], status_code=307)

    # кэша нет - идем в бд
    link = await get_link_or_404(short_code, db)

    # проверяем не истекла ли ссылка
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        expired = ExpiredLink(
            short_code=link.short_code,
            original_url=link.original_url,
            user_id=link.user_id,
            created_at=link.created_at,
            use_count=link.use_count,
            reason="expired",
        )
        db.add(expired)
        await db.delete(link)
        await db.commit()
        raise HTTPException(status_code=410, detail="link has expired")

    # кэшируем урл для будущих запросов
    await cache_set(f"link:{short_code}", {"original_url": link.original_url}, ttl=REDIRECT_CACHE_TTL)

    link.use_count += 1
    link.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return RedirectResponse(url=link.original_url, status_code=307)

@router.delete("/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    # удаление ссылки, только владелец может удалить
    link = await get_link_or_404(short_code, db)

    if link.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not your link")

    expired = ExpiredLink(
        short_code=link.short_code,
        original_url=link.original_url,
        user_id=link.user_id,
        created_at=link.created_at,
        use_count=link.use_count,
        reason="deleted",
    )
    db.add(expired)
    await db.delete(link)
    await db.commit()
    # чистим кэш после удаления
    await invalidate_link_cache(short_code)

@router.put("/{short_code}", response_model=LinkOut)
async def update_link(
    short_code: str,
    data: LinkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    # обновление ссылки - можно поменять оригинальный юрл или сам short_code
    link = await get_link_or_404(short_code, db)

    if link.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not your link")

    if data.original_url is not None:
        link.original_url = str(data.original_url)

    if data.short_code is not None:
        existing = await db.execute(select(Link).where(Link.short_code == data.short_code))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="this short code is already taken")
        link.short_code = data.short_code

    await db.commit()
    await db.refresh(link)
    # инвалидируем кэш по старому коду (и новому на всякий случай)
    await invalidate_link_cache(short_code)
    if data.short_code:
        await invalidate_link_cache(data.short_code)
    return link
