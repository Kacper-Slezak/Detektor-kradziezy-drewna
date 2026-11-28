import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.deps import PendingPasswordUser
from app.models import Range, User
from app.schemas import ChangePasswordIn, LoginIn, LoginOut, ProfileOut, RangeOut
from app.security import DUMMY_HASH, create_token, hash_password, verify_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]

# Nieudane logowania: login -> czasy prób (time.monotonic). Licznik per login, nie per IP:
# za proxy adres klienta da się podrobić nagłówkiem X-Forwarded-For.
# Pamięć procesu, więc działa przy jednym workerze uvicorn (tak jest w compose);
# restart backendu zeruje liczniki.
_failures: dict[str, list[float]] = {}


def _recent_failures(key: str, now: float) -> list[float]:
    recent = [t for t in _failures.get(key, []) if now - t < settings.login_window_s]
    if recent:
        _failures[key] = recent
    else:
        _failures.pop(key, None)
    return recent


def _forget_old(now: float) -> None:
    """Bez tego losowe loginy zapełniałyby słownik w nieskończoność."""
    for key in list(_failures):
        _recent_failures(key, now)


async def _profile(session: AsyncSession, user: User) -> ProfileOut:
    range_ = await session.get(Range, user.range_id) if user.range_id is not None else None
    return ProfileOut(
        id=user.id,
        login=user.login,
        full_name=user.full_name,
        role=user.role,
        range=RangeOut.model_validate(range_) if range_ else None,
        must_change_password=user.must_change_password,
    )


@router.post(
    "/login",
    response_model=LoginOut,
    responses={
        401: {"description": "Zły login lub hasło"},
        429: {"description": "Za dużo nieudanych prób dla tego loginu"},
    },
)
async def login(body: LoginIn, session: Session) -> LoginOut:
    key = body.login.strip().lower()
    now = time.monotonic()
    recent = _recent_failures(key, now)
    if len(recent) >= settings.login_max_failures:
        retry_after = int(settings.login_window_s - (now - recent[0])) + 1
        log.warning("Logowanie zablokowane: %s (%d prób)", body.login, len(recent))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Za dużo nieudanych prób, spróbuj za {retry_after // 60 + 1} min",
            headers={"Retry-After": str(retry_after)},
        )

    user = await session.scalar(select(User).where(User.login == body.login))
    password_ok = await verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if user is None or not password_ok or not user.active:
        log.warning("Nieudane logowanie: %s", body.login)
        if len(_failures) > 1000:
            _forget_old(now)
        _failures.setdefault(key, []).append(now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny login lub hasło")

    _failures.pop(key, None)

    token, expires_at = create_token(user.id)
    return LoginOut(token=token, expires_at=expires_at, user=await _profile(session, user))


@router.get("/me", response_model=ProfileOut)
async def me(user: PendingPasswordUser, session: Session) -> ProfileOut:
    return await _profile(session, user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"description": "Złe stare hasło albo nowe takie samo jak stare"}},
)
async def change_password(body: ChangePasswordIn, user: PendingPasswordUser, session: Session) -> None:
    if not await verify_password(user.password_hash, body.old_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Błędne stare hasło")
    if body.new_password == body.old_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nowe hasło musi się różnić od starego")

    user.password_hash = await hash_password(body.new_password)
    user.must_change_password = False
    await session.commit()
    log.info("Użytkownik %s zmienił hasło", user.login)
