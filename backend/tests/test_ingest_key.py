"""Klucz X-Ingest-Key dla POST /api/v1/ingest."""

import logging

import pytest

from app.config import settings
from tests.conftest import SENSOR_ID
from tools.simulator import parse_args

FRAME = {"device": SENSOR_ID, "payload_hex": "130001010158"}  # BOOT
KEY = "klucz-urzadzen-123"


@pytest.fixture
def ingest_key(monkeypatch):
    monkeypatch.setattr(settings, "ingest_api_key", KEY)


async def test_dobry_klucz(client, ingest_key):
    r = await client.post("/api/v1/ingest", json=FRAME, headers={"X-Ingest-Key": KEY})
    assert r.status_code == 201, r.text


async def test_brak_klucza_401(client, ingest_key):
    r = await client.post("/api/v1/ingest", json=FRAME)
    assert r.status_code == 401
    assert "X-Ingest-Key" in r.json()["detail"]


@pytest.mark.parametrize("bad", ["zly", "", KEY + "x", KEY.upper()])
async def test_zly_klucz_401(client, ingest_key, bad):
    r = await client.post("/api/v1/ingest", json=FRAME, headers={"X-Ingest-Key": bad})
    assert r.status_code == 401


async def test_klucz_sprawdzany_przed_ramka(client, ingest_key):
    # bez klucza nie zdradzamy, czy czujnik istnieje albo ramka jest poprawna
    r = await client.post(
        "/api/v1/ingest", json={"device": "FFFFFFFFFFFFFFFF", "payload_hex": "zz"}
    )
    assert r.status_code in (401, 422)
    r = await client.post(
        "/api/v1/ingest", json={"device": "FFFFFFFFFFFFFFFF", "payload_hex": "13"}
    )
    assert r.status_code == 401


async def test_bez_skonfigurowanego_klucza_przepuszcza(client):
    assert settings.ingest_api_key == ""
    r = await client.post("/api/v1/ingest", json=FRAME)
    assert r.status_code == 201


async def test_klucz_nie_dotyczy_innych_endpointow(client, ingest_key):
    assert (await client.get("/health")).status_code == 200


async def test_klucz_w_swaggerze(client):
    schema = (await client.get("/openapi.json")).json()
    assert (
        schema["components"]["securitySchemes"]["APIKeyHeader"]["name"]
        == "X-Ingest-Key"
    )


def test_symulator_bierze_klucz_ze_srodowiska(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", KEY)
    assert parse_args([]).ingest_key == KEY
    assert parse_args(["--ingest-key", "inny"]).ingest_key == "inny"


async def test_symulator_z_kluczem(client, ingest_key, tmp_path, caplog):
    import httpx

    from app.main import app
    from tools.simulator import run

    args = parse_args(
        [
            "--sensors",
            SENSOR_ID,
            "--once",
            "--wait",
            "0",
            "--state",
            str(tmp_path / "s.json"),
            "--alarm-chance",
            "0",
            "--ingest-key",
            KEY,
        ]
    )
    headers = {"X-Ingest-Key": args.ingest_key}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", headers=headers
    ) as c:
        with caplog.at_level(logging.ERROR, logger="simulator"):
            await run(args, c)
    assert "odrzucił klucz" not in caplog.text


async def test_symulator_bez_klucza_loguje_blad(client, ingest_key, tmp_path, caplog):
    from tools.simulator import run

    args = parse_args(
        [
            "--sensors",
            SENSOR_ID,
            "--once",
            "--wait",
            "0",
            "--state",
            str(tmp_path / "s.json"),
            "--alarm-chance",
            "0",
            "--ingest-key",
            "",
        ]
    )
    with caplog.at_level(logging.ERROR, logger="simulator"):
        await run(args, client)
    assert "odrzucił klucz" in caplog.text
