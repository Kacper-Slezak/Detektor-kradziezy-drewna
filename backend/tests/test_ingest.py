from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Alarm, Message, Release, Sensor
from tests.conftest import SENSOR_ID

T0 = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)


def frame(payload: str, counter: int) -> str:
    """Podmienia licznik (bajty 1-2) w ramce."""
    return payload[:2] + f"{counter:04X}" + payload[6:]


ALARM = "11002A0101570028B440"
HEARTBEAT = "120000400C00"


async def post(client, payload, at=T0, device=SENSOR_ID):
    return await client.post(
        "/api/v1/ingest",
        json={"device": device, "payload_hex": payload, "received_at": at.isoformat(), "rssi": -112},
    )


async def count(session_maker, model):
    async with session_maker() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def test_alarm_tworzy_alarm(client, session_maker):
    r = await post(client, ALARM)
    assert r.status_code == 201
    body = r.json()
    assert body["alarm_created"] is True and body["alarm_id"] is not None
    assert await count(session_maker, Message) == 1
    assert await count(session_maker, Alarm) == 1


async def test_powtorzenia_scalane_w_jeden_alarm(client, session_maker):
    # ALARM wysyłany 3x, każdy z kolejnym licznikiem
    ids = set()
    for i, minutes in enumerate([0, 1, 5]):
        r = await post(client, frame(ALARM, 42 + i), at=T0 + timedelta(minutes=minutes))
        assert r.status_code == 201
        ids.add(r.json()["alarm_id"])

    assert len(ids) == 1
    assert await count(session_maker, Alarm) == 1
    assert await count(session_maker, Message) == 3
    async with session_maker() as s:
        alarm = await s.scalar(select(Alarm))
        assert alarm.repeats == 3


async def test_alarm_po_oknie_to_nowy_alarm(client, session_maker):
    await post(client, frame(ALARM, 1), at=T0)
    await post(client, frame(ALARM, 2), at=T0 + timedelta(hours=2))
    assert await count(session_maker, Alarm) == 2


async def test_duplikat_licznika_pomijany(client, session_maker):
    assert (await post(client, ALARM)).status_code == 201
    r = await post(client, ALARM)  # ta sama ramka drugi raz
    assert r.status_code == 200
    assert r.json()["status"] == "duplicate"
    assert await count(session_maker, Message) == 1


async def test_boot_resetuje_licznik(client, session_maker):
    await post(client, frame(HEARTBEAT, 500))
    assert (await post(client, frame("130000050163", 0))).status_code == 201  # BOOT
    assert (await post(client, frame(HEARTBEAT, 1))).status_code == 201
    assert await count(session_maker, Message) == 3


async def test_przekrecenie_licznika(client, session_maker):
    await post(client, frame(HEARTBEAT, 65535))
    assert (await post(client, frame(HEARTBEAT, 0))).status_code == 201


async def test_heartbeat_aktualizuje_czujnik(client, session_maker):
    r = await post(client, HEARTBEAT)
    assert r.status_code == 201
    assert r.json()["alarm_id"] is None
    async with session_maker() as s:
        sensor = await s.get(Sensor, SENSOR_ID)
        assert sensor.battery_pct == 64
        assert sensor.last_seen is not None


async def test_nieznany_czujnik_404(client):
    r = await post(client, ALARM, device="NIEMA")
    assert r.status_code == 404


async def test_bledna_ramka_422(client, session_maker):
    r = await post(client, "21002A0101570028B440")
    assert r.status_code == 422
    assert "wersja" in r.json()["detail"]
    assert await count(session_maker, Message) == 0


async def test_wyciszony_czujnik_bez_alarmu(client, session_maker):
    async with session_maker() as s:
        s.add(Release(sensor_id=SENSOR_ID, starts_at=T0 - timedelta(hours=1),
                      ends_at=T0 + timedelta(hours=3)))
        await s.commit()

    r = await post(client, ALARM)
    assert r.status_code == 201
    assert r.json()["muted"] is True
    assert await count(session_maker, Message) == 1
    assert await count(session_maker, Alarm) == 0


async def test_wylaczony_czujnik_bez_alarmu(client, session_maker):
    async with session_maker() as s:
        (await s.get(Sensor, SENSOR_ID)).active = False
        await s.commit()

    r = await post(client, ALARM)
    assert r.json()["muted"] is True
    assert await count(session_maker, Alarm) == 0


async def test_bez_czasu_odbioru_bierze_teraz(client, session_maker):
    r = await client.post("/api/v1/ingest", json={"device": SENSOR_ID, "payload_hex": ALARM})
    assert r.status_code == 201
    assert r.json()["alarm_created"] is True
