import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import PendingPasswordUser
from app.models import Range, User
from app.schemas import ChangePasswordIn, LoginIn, LoginOut, ProfileOut, RangeOut
from app.security import DUMMY_HASH, create_token, hash_password, verify_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]


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


@router.post("/login", response_model=LoginOut, responses={401: {"description": "Zły login lub hasło"}})
async def login(body: LoginIn, session: Session) -> LoginOut:
    user = await session.scalar(select(User).where(User.login == body.login))
    password_ok = await verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if user is None or not password_ok or not user.active:
        log.warning("Nieudane logowanie: %s", body.login)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny login lub hasło")

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
