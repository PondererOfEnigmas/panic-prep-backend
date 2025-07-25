from datetime import date

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from pydantic import BaseModel
from supabase import Client, create_client

from src.config import settings


# data models
class User(BaseModel):
    """
    Minimal user object propagated through request handlers.
    Extend with more fields if you need them.
    """

    id: str
    email: str | None = None
    role: str | None = None


# helpers / dependencies
_auth_scheme = HTTPBearer(auto_error=True)


async def verify_token(token: str) -> dict:
    """
    Call Supabase `/auth/v1/user` to validate JWT bearer token.
    Returns raw user JSON on success, raises HTTPException on failure.
    """
    url = f"{settings.supabase_url}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": settings.supabase_anon_key,  # public anon key is required
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=10)

    if resp.status_code != 200:
        logger.warning(
            "Supabase token verification failed – %s %s", resp.status_code, resp.text
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired access token",
        )

    data = resp.json()
    if not data or "id" not in data:
        logger.warning("Supabase /auth/v1/user payload unexpected: %s", data)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Malformed token payload",
        )

    return data


async def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(_auth_scheme),
) -> User:
    """
    FastAPI dependency.
    On success returns a `User` instance; otherwise raises 403/401.
    """
    raw = await verify_token(cred.credentials)
    return User(id=raw["id"], email=raw.get("email"), role=raw.get("role"))


# day generation cap
async def check_generation_limit(user: User = Depends(get_current_user)) -> None:
    """
    Dependency to ensure the caller has not exceeded
    `settings.max_gen_per_day` slide / presentation builds today.
    """
    supabase: Client = create_client(
        settings.supabase_url, settings.supabase_service_key
    )
    today = date.today().isoformat()

    # Fetch current count
    res = (
        supabase.table("daily_generations")
        .select("count")
        .eq("user_id", user.id)
        .eq("generation_date", today)
        .execute()
    )

    current = res.data[0]["count"] if res.data else 0

    if settings.dev_mode:
        return

    if current >= settings.max_gen_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily generation limit ({settings.max_gen_per_day}) reached",
        )

    # Upsert with incremented count
    if current == 0:
        supabase.table("daily_generations").insert(
            {"user_id": user.id, "generation_date": today, "count": 1}
        ).execute()
    else:
        supabase.table("daily_generations").update({"count": current + 1}).eq(
            "user_id", user.id
        ).eq("generation_date", today).execute()
