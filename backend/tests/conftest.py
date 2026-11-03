"""Testy na SQLite w pamięci – nie potrzebują Dockera ani Postgresa."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import Range, Sensor, User
from app.security import hash_password
from tests.utils import PASSWORD, auth

SENSOR_ID = "70B3D57ED0051234"


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    # niezależnie od tego, co jest w lokalnym .env
    monkeypatch.setattr(settings, "jwt_secret", "tajny-klucz-do-testow-minimum-32-bajty")


@pytest.fixture
async def session_maker():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # SQLite domyślnie nie sprawdza kluczy obcych, a Postgres tak - testy mają łapać te same błędy
    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(Sensor(id=SENSOR_ID, name="Skład przy drodze 5", lat=50.06, lon=19.94))
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.fixture
async def client(session_maker):
    async def _session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def make_user(session_maker):
    """Tworzy użytkownika w bazie i zwraca jego id."""

    async def _make(login="blazej", role="forester", range_id=None, **kwargs) -> int:
        kwargs.setdefault("must_change_password", False)
        async with session_maker() as s:
            user = User(
                login=login,
                password_hash=await hash_password(PASSWORD),
                full_name=f"Imię {login}",
                role=role,
                range_id=range_id,
                **kwargs,
            )
            s.add(user)
            await s.commit()
            return user.id

    return _make


@pytest.fixture
async def range_id(session_maker) -> int:
    async with session_maker() as s:
        r = Range(name="Leśnictwo Dąbrowa")
        s.add(r)
        await s.commit()
        return r.id


@pytest.fixture
async def admin(client, make_user):
    await make_user("admin", role="admin")
    return await auth(client, "admin")
