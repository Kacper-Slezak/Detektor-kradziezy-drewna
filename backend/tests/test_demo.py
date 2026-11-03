"""Seed danych demo: każdy czujnik ma mieć zamierzony stan, a historia ma przejść przez /ingest."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.demo import DEMO_PREFIX, DEMO_SENSORS, create_demo, demo_exists, reset_demo
from app.models import Alarm, Message, Release, Sensor, User
from app.protocol.decoder import decode_hex
from tests.utils import auth

NOW = datetime.now(UTC)

EXPECTED_STATE = {
    "ok": "ok",
    "alarm": "alarm",
    "muted": "muted",
    "silent": "silent",
    "low_battery": "ok",
    "off": "inactive",
    "unmounted": "inactive",
    "bench": "inactive",
}


@pytest.fixture
async def demo(session_maker):
    async with session_maker() as s:
        return await create_demo(s, now=NOW)


async def _demo_auth(client, login):
    return await auth(client, login, settings.seed_demo_password)


async def _states(client, login) -> dict[str, dict]:
    r = await client.get("/api/v1/sensors", headers=await _demo_auth(client, login))
    assert r.status_code == 200, r.text
    return {s["id"]: s for s in r.json() if s["id"].startswith(DEMO_PREFIX)}


async def test_kazdy_czujnik_ma_zamierzony_stan(client, demo):
    sensors = await _states(client, "bogdan")  # nadleśniczy widzi wszystko
    assert len(sensors) == len(DEMO_SENSORS)
    for s in DEMO_SENSORS:
        assert sensors[s.id]["state"] == EXPECTED_STATE[s.scenario], s.scenario


async def test_lesniczy_widza_swoje_lesnictwa(client, demo):
    dabrowa = await _states(client, "blazej")
    olszyny = await _states(client, "ola")
    assert len(dabrowa) == 7
    assert len(olszyny) == 3
    assert not set(dabrowa) & set(olszyny)


async def test_konta_demo_bez_wymuszonej_zmiany_hasla(client, demo):
    r = await client.get("/api/v1/auth/me", headers=await _demo_auth(client, "blazej"))
    assert r.json()["must_change_password"] is False


async def test_niska_bateria_i_wyciszenie(client, demo):
    sensors = await _states(client, "blazej")
    low = next(s for s in DEMO_SENSORS if s.scenario == "low_battery")
    assert sensors[low.id]["battery_pct"] < 20
    muted = next(s for s in DEMO_SENSORS if s.scenario == "muted")
    assert sensors[muted.id]["muted_until"] is not None


async def test_historia_przeszla_przez_ingest(session_maker, demo):
    async with session_maker() as s:
        messages = list(await s.scalars(select(Message)))
        assert len(messages) == demo["frames"]
        # każda zapisana ramka jest poprawna wg dekodera
        for m in messages:
            decode_hex(m.payload_hex)
        alarms = list(await s.scalars(select(Alarm)))
        # otwarty alarm + zamknięta kradzież + zamknięty fałszywy; alarm w trakcie wydania nie powstał
        assert sorted(a.status for a in alarms) == ["false_alarm", "new", "theft"]
        assert all(a.repeats == 3 for a in alarms)
        closed = [a for a in alarms if a.status != "new"]
        assert all(a.response_by and a.response_at and a.response_lat for a in closed)
        assert await s.scalar(select(func.count(Release.id))) == 2


async def test_czujnik_na_biurku_i_niezamontowany(session_maker, demo):
    async with session_maker() as s:
        bench = next(x for x in DEMO_SENSORS if x.scenario == "bench")
        unmounted = next(x for x in DEMO_SENSORS if x.scenario == "unmounted")
        assert (await s.get(Sensor, bench.id)).last_seen is not None
        assert (await s.get(Sensor, unmounted.id)).last_seen is None


async def test_reset_usuwa_tylko_dane_demo(session_maker, demo, make_user):
    await make_user("admin", role="admin")
    async with session_maker() as s:
        assert await demo_exists(s)
        await reset_demo(s)
        assert not await demo_exists(s)
        assert await s.scalar(select(func.count(Message.id))) == 0
        logins = set(await s.scalars(select(User.login)))
        assert logins == {"admin"}
        # czujnik z conftest (nie demo) zostaje
        assert await s.scalar(select(func.count(Sensor.id))) == 1
        # i można utworzyć od nowa
        result = await create_demo(s, now=NOW)
        assert result["sensors"] == len(DEMO_SENSORS)


async def test_istniejace_konto_nie_jest_nadpisywane(session_maker, make_user):
    await make_user("blazej", role="admin")
    async with session_maker() as s:
        result = await create_demo(s, now=NOW)
        assert result["users"] == 2
        assert await s.scalar(select(User.role).where(User.login == "blazej")) == "admin"
