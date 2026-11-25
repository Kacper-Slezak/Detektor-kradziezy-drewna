"""GET /api/v1/admin/logs: recent log lines from memory, admin only."""

import logging

from app.routers.admin import buffer
from tests.utils import auth


async def test_admin_widzi_ostatnie_logi(client, admin):
    buffer.lines.clear()
    logging.getLogger("app.test").warning("pierwsza")
    logging.getLogger("app.test").error("druga")

    r = await client.get("/api/v1/admin/logs?tail=2", headers=admin)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    lines = r.text.splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("WARNING app.test: pierwsza")
    assert lines[1].endswith("ERROR app.test: druga")


async def test_uvicorn_access_bez_health(client, admin):
    buffer.lines.clear()
    access = logging.getLogger("uvicorn.access")
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/health", "1.1", 200)
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/api/v1/x", "1.1", 500)

    r = await client.get("/api/v1/admin/logs", headers=admin)
    assert "/health" not in r.text
    assert '"GET /api/v1/x HTTP/1.1" 500' in r.text


async def test_lesniczy_nie_widzi_logow(client, make_user, range_id):
    await make_user("blazej", role="forester", range_id=range_id)
    r = await client.get("/api/v1/admin/logs", headers=await auth(client, "blazej"))
    assert r.status_code == 403


async def test_bez_tokenu_401(client):
    r = await client.get("/api/v1/admin/logs")
    assert r.status_code == 401
