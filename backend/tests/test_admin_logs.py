"""GET /api/v1/admin/logs: recent log records from memory, admin only."""

import logging

from app.routers.admin import buffer
from tests.utils import auth


async def test_admin_widzi_ostatnie_logi(client, admin):
    buffer.lines.clear()
    logging.getLogger("app.test").warning("pierwsza %s", 1)
    try:
        raise ValueError("zepsute")
    except ValueError:
        logging.getLogger("app.test").exception("druga")

    r = await client.get("/api/v1/admin/logs?tail=2", headers=admin)
    assert r.status_code == 200
    first, second = r.json()
    assert first["level"] == "WARNING"
    assert first["logger"] == "app.test"
    assert first["message"] == "pierwsza 1"
    assert first["time"].endswith("Z")
    assert second["level"] == "ERROR"
    assert second["message"].startswith("druga\nTraceback")
    assert "ValueError: zepsute" in second["message"]


async def test_tail_ogranicza_liczbe(client, admin):
    buffer.lines.clear()
    for i in range(5):
        logging.getLogger("app.test").info("linia %d", i)
    r = await client.get("/api/v1/admin/logs?tail=2", headers=admin)
    assert [line["message"] for line in r.json()] == ["linia 3", "linia 4"]


async def test_uvicorn_access_bez_health(client, admin):
    buffer.lines.clear()
    access = logging.getLogger("uvicorn.access")
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/health", "1.1", 200)
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/api/v1/x", "1.1", 500)

    r = await client.get("/api/v1/admin/logs", headers=admin)
    messages = [line["message"] for line in r.json()]
    assert not any("/health" in m for m in messages)
    assert '1.2.3.4:5 - "GET /api/v1/x HTTP/1.1" 500' in messages


async def test_lesniczy_nie_widzi_logow(client, make_user, range_id):
    await make_user("blazej", role="forester", range_id=range_id)
    r = await client.get("/api/v1/admin/logs", headers=await auth(client, "blazej"))
    assert r.status_code == 403


async def test_bez_tokenu_401(client):
    r = await client.get("/api/v1/admin/logs")
    assert r.status_code == 401


async def test_wylaczone_flaga_404(client, admin, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_logs_enabled", False)
    r = await client.get("/api/v1/admin/logs", headers=admin)
    assert r.status_code == 404
