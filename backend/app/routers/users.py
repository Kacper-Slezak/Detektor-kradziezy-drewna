import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import AdminUser
from app.models import Range, User
from app.schemas import RangeOut, TempPasswordOut, UserCreate, UserOut, UserPatch
from app.security import generate_temp_password, hash_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["users"])

Session = Annotated[AsyncSession, Depends(get_session)]


async def _check_role_and_range(session: AsyncSession, role: str, range_id: int | None) -> None:
    """Leśniczy musi mieć leśnictwo, a podane leśnictwo musi istnieć."""
    if role == "forester" and range_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leśniczy musi mieć przypisane leśnictwo")
    if range_id is not None and await session.get(Range, range_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Nie ma leśnictwa o id {range_id}")


@router.get("/users", response_model=list[UserOut])
async def list_users(_: AdminUser, session: Session) -> list[User]:
    return list((await session.scalars(select(User).order_by(User.id))).all())


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "Złe leśnictwo"}, 409: {"description": "Login zajęty"}},
)
async def create_user(body: UserCreate, _: AdminUser, session: Session) -> User:
    if await session.scalar(select(User.id).where(User.login == body.login)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Login {body.login} jest już zajęty")
    await _check_role_and_range(session, body.role, body.range_id)

    user = User(
        login=body.login,
        full_name=body.full_name,
        role=body.role,
        range_id=body.range_id,
        password_hash=await hash_password(body.password),
        must_change_password=True,  # hasło zna admin, więc użytkownik ustawia własne
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # ktoś zajął login między sprawdzeniem a zapisem
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Login {body.login} jest już zajęty") from None
    log.info("Utworzono użytkownika %s (%s)", user.login, user.role)
    return user


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    responses={409: {"description": "Admin nie może dezaktywować ani zdegradować samego siebie"}},
)
async def update_user(user_id: int, body: UserPatch, admin: AdminUser, session: Session) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego użytkownika")

    changes = body.model_dump(exclude_unset=True)
    for field in ("full_name", "role", "active"):
        if field in changes and changes[field] is None:
            del changes[field]

    if user.id == admin.id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nie możesz dezaktywować ani zdegradować własnego konta")
    
    if "role" in changes or "range_id" in changes:
        await _check_role_and_range(
            session, changes.get("role", user.role), changes.get("range_id", user.range_id)
        )
    for field, value in changes.items():
        setattr(user, field, value)
    await session.commit()
    log.info("Admin %s zmienił użytkownika %s: %s", admin.login, user.login, sorted(changes))
    return user


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordOut)
async def reset_password(user_id: int, admin: AdminUser, session: Session) -> TempPasswordOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego użytkownika")

    temporary = generate_temp_password()
    user.password_hash = await hash_password(temporary)
    user.must_change_password = True
    await session.commit()
    log.info("Admin %s zresetował hasło użytkownika %s", admin.login, user.login)
    return TempPasswordOut(temporary_password=temporary)


@router.get("/ranges", response_model=list[RangeOut])
async def list_ranges(_: AdminUser, session: Session) -> list[Range]:
    return list((await session.scalars(select(Range).order_by(Range.id))).all())
