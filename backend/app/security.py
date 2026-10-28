"""Hasła (argon2) i tokeny JWT."""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

ALGORITHM = "HS256"

_hasher = PasswordHasher()

DUMMY_HASH = _hasher.hash("brak-takiego-konta")

_TEMP_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    return await asyncio.to_thread(_verify, password_hash, password)


def generate_temp_password() -> str:
    """Np. `Xk7p-Q2mR-9tWz`."""
    groups = ("".join(secrets.choice(_TEMP_ALPHABET) for _ in range(4)) for _ in range(3))
    return "-".join(groups)


def _secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("Brak JWT_SECRET w ustawieniach (.env)")
    return settings.jwt_secret


def create_token(user_id: int) -> tuple[str, datetime]:
    """Zwraca (token, kiedy wygasa)."""
    expires_at = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)
    token = jwt.encode({"sub": str(user_id), "exp": expires_at}, _secret(), algorithm=ALGORITHM)
    return token, expires_at


def decode_token(token: str) -> int | None:
    """Id użytkownika z tokena albo None, gdy token jest zły lub wygasł."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None
