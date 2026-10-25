"""Dane startowe: konto admina. Uruchom: `python -m app.seed` (w Dockerze: `docker compose run --rm web python -m app.seed`).

Bezpieczne do powtarzania - jeśli admin już istnieje, nic nie robi.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal, engine
from app.models import User
from app.security import generate_temp_password, hash_password


async def create_admin(session: AsyncSession) -> tuple[bool, str | None]:
    """Tworzy admina. Zwraca (czy_utworzono, hasło_jeśli_wylosowane)."""
    login = settings.seed_admin_login
    if await session.scalar(select(User.id).where(User.login == login)):
        return False, None

    generated = None if settings.seed_admin_password else generate_temp_password()
    session.add(
        User(
            login=login,
            password_hash=await hash_password(settings.seed_admin_password or generated),
            full_name="Administrator",
            role="admin",
            must_change_password=True,  # hasło startowe trzeba zmienić przy pierwszym logowaniu
        )
    )
    await session.commit()
    return True, generated


async def main() -> None:
    async with SessionLocal() as session:
        created, generated = await create_admin(session)
    await engine.dispose()

    login = settings.seed_admin_login
    if not created:
        print(f"Admin '{login}' już istnieje - nic nie zmieniono.")
    elif generated:
        print(f"Utworzono admina '{login}', hasło tymczasowe: {generated}")
    else:
        print(f"Utworzono admina '{login}' z hasłem z SEED_ADMIN_PASSWORD.")


if __name__ == "__main__":
    asyncio.run(main())
