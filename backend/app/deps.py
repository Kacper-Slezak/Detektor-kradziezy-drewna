"""Zależności FastAPI: kto jest zalogowany i jaką ma rolę."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False, description="Token z `POST /api/v1/auth/login`")

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


async def user_allowing_password_change(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Zalogowany użytkownik, także gdy musi jeszcze zmienić hasło.

    Tylko dla `/auth/me` i `/auth/change-password`. Reszta bierze `CurrentUser`.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak tokena", headers=_UNAUTHORIZED)
    user_id = decode_token(credentials.credentials)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None or not user.active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token nieważny lub wygasł", headers=_UNAUTHORIZED
        )
    return user


async def current_user(
    user: Annotated[User, Depends(user_allowing_password_change)],
) -> User:
    if user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Najpierw zmień hasło")
    return user


def require_role(*roles: str):
    async def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak uprawnień")
        return user

    return check


PendingPasswordUser = Annotated[User, Depends(user_allowing_password_change)]
CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_role("admin"))]
