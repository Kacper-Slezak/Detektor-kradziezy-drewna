"""Dane startowe. Uruchom w Dockerze: `docker compose run --rm web python -m app.seed [opcje]`.

    python -m app.seed                  # admin + leśnictwa
    python -m app.seed --demo           # + konta demo, czujniki w każdym stanie, historia 7 dni
    python -m app.seed --demo --reset   # usuwa dane demo i tworzy je od nowa (np. gdy się zestarzały)

Bezpieczne do powtarzania - jeśli admin albo dane demo już istnieją, nic nie zmienia.
"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal, engine
from app.demo import DEMO_USERS, create_demo, demo_exists, reset_demo
from app.models import Range, User
from app.security import generate_temp_password, hash_password

DEFAULT_RANGES = ["Leśnictwo Dąbrowa", "Leśnictwo Olszyny"]


async def create_ranges(session: AsyncSession) -> int:
    """Przykładowe leśnictwa. Zwraca, ile dodano."""
    added = 0
    for name in DEFAULT_RANGES:
        if not await session.scalar(select(Range.id).where(Range.name == name)):
            session.add(Range(name=name))
            added += 1
    await session.commit()
    return added


async def create_admin(session: AsyncSession) -> tuple[bool, str | None]:
    """Tworzy admina. Zwraca (czy_utworzono, hasło_jeśli_wylosowane)."""
    login = settings.seed_admin_login
    if await session.scalar(select(User.id).where(User.login == login)):
        return False, None

    generated = None if settings.seed_admin_password else generate_temp_password()
    session.add(
        User(
            login=login,
            password_hash=await hash_password(
                settings.seed_admin_password or generated
            ),
            full_name="Administrator",
            role="admin",
            must_change_password=True,  # hasło startowe trzeba zmienić przy pierwszym logowaniu
        )
    )
    await session.commit()
    return True, generated


async def main(demo: bool = False, reset: bool = False) -> None:
    async with SessionLocal() as session:
        await create_ranges(session)
        created, generated = await create_admin(session)
        demo_result = None
        if demo:
            if reset:
                await reset_demo(session)
            if not await demo_exists(session):
                demo_result = await create_demo(session)
    await engine.dispose()

    login = settings.seed_admin_login
    if not created:
        print(f"Admin '{login}' już istnieje - nic nie zmieniono.")
    elif generated:
        print(f"Utworzono admina '{login}', hasło tymczasowe: {generated}")
    else:
        print(f"Utworzono admina '{login}' z hasłem z SEED_ADMIN_PASSWORD.")

    if demo and demo_result is None:
        print("Dane demo już są - nic nie zmieniono. Odświeżenie: --demo --reset")
    elif demo_result:
        print(
            f"Dane demo: {demo_result['sensors']} czujników, {demo_result['frames']} ramek, "
            f"nowe konta: {demo_result['users']}."
        )
        logins = ", ".join(login for login, *_ in DEMO_USERS)
        print(f"Konta demo ({logins}), hasło: {settings.seed_demo_password}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dane startowe bazy")
    parser.add_argument(
        "--demo", action="store_true", help="dane demo: konta, czujniki, historia"
    )
    parser.add_argument(
        "--reset", action="store_true", help="z --demo: usuń dane demo i utwórz od nowa"
    )
    args = parser.parse_args()
    if args.reset and not args.demo:
        parser.error("--reset działa tylko z --demo")
    asyncio.run(main(demo=args.demo, reset=args.reset))
