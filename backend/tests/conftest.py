"""Testy na SQLite w pamięci – nie potrzebują Dockera ani Postgresa."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import Sensor

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
