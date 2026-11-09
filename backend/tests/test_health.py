"""GET /health: ok tylko wtedy, gdy baza odpowiada (monitoring, healthcheck w compose)."""

from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app


async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_bez_bazy_503(client):
    class BrokenSession:
        async def execute(self, *_):
            raise OperationalError("SELECT 1", {}, ConnectionRefusedError())

    async def _broken():
        yield BrokenSession()

    app.dependency_overrides[get_session] = _broken
    r = await client.get("/health")
    assert r.status_code == 503
    assert r.json()["detail"] == "Baza danych niedostępna"
