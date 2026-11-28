"""Alarmy: lista, szczegóły, odpowiedź leśniczego (api.md, sekcja 4)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Alarm, Range, Sensor
from tests.utils import auth

NOW = datetime.now(UTC)
DABROWA_SENSOR = "70B3D57ED0000001"
OLSZYNY_SENSOR = "70B3D57ED0000002"


def _alarm(sensor_id, minutes_ago, **kwargs) -> Alarm:
    at = NOW - timedelta(minutes=minutes_ago)
    defaults = {
        "started_at": at,
        "last_frame_at": at + timedelta(seconds=60),
        "event_type": 1,
        "sources": ["microphone", "vibration"],
        "confidence": 87,
        "duration_s": 40,
        "energy": 180,
        "repeats": 3,
    }
    return Alarm(sensor_id=sensor_id, **(defaults | kwargs))


@pytest.fixture
async def alarms(session_maker) -> dict[str, int]:
    """Dąbrowa: nowy (10 min), fałszywy z samych wibracji (2 dni), kradzież (5 dni).
    Olszyny: nowy (30 min)."""
    async with session_maker() as s:
        dabrowa, olszyny = Range(name="Leśnictwo Dąbrowa"), Range(name="Leśnictwo Olszyny")
        s.add_all([dabrowa, olszyny])
        await s.flush()
        s.add_all(
            [
                Sensor(id=DABROWA_SENSOR, name="Skład 5", range_id=dabrowa.id, lat=50.06, lon=20.31),
                Sensor(id=OLSZYNY_SENSOR, name="Kopiec", range_id=olszyny.id, lat=50.04, lon=20.41),
            ]
        )
        await s.flush()
        rows = {
            "new": _alarm(DABROWA_SENSOR, 10),
            "false": _alarm(
                DABROWA_SENSOR,
                60 * 48,
                sources=["vibration"],
                confidence=50,
                status="false_alarm",
                response_by="blazej",
                response_at=NOW - timedelta(days=2) + timedelta(minutes=40),
                response_comment="zwierzę przy stosie",
                response_lat=50.0601,
                response_lon=20.3102,
            ),
            "theft": _alarm(DABROWA_SENSOR, 60 * 120, status="theft", response_by="blazej", response_at=NOW),
            "olszyny": _alarm(OLSZYNY_SENSOR, 30, event_type=7),
        }
        s.add_all(rows.values())
        await s.commit()
        return {k: a.id for k, a in rows.items()}


@pytest.fixture
async def forester(client, make_user, alarms, session_maker):
    async with session_maker() as s:
        range_id = (await s.get(Sensor, DABROWA_SENSOR)).range_id
    await make_user("blazej", role="forester", range_id=range_id)
    return await auth(client, "blazej")


@pytest.fixture
async def manager(client, make_user, alarms):
    await make_user("bogdan", role="district_manager")
    return await auth(client, "bogdan")


async def _ids(client, headers, **params) -> list[int]:
    r = await client.get("/api/v1/alarms", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return [a["id"] for a in r.json()]


# --- GET /alarms ---


async def test_lista_wymaga_logowania(client):
    assert (await client.get("/api/v1/alarms")).status_code == 401


async def test_lesniczy_widzi_swoje_od_najnowszych(client, forester, alarms):
    assert await _ids(client, forester) == [alarms["new"], alarms["false"], alarms["theft"]]


async def test_nadlesniczy_i_admin_widza_wszystko(client, manager, admin, alarms):
    expected = [alarms["new"], alarms["olszyny"], alarms["false"], alarms["theft"]]
    assert await _ids(client, manager) == expected
    assert await _ids(client, admin) == expected


async def test_lesniczy_bez_lesnictwa_nie_widzi_nic(client, make_user, alarms):
    await make_user("bez", role="forester")
    assert await _ids(client, await auth(client, "bez")) == []


async def test_ksztalt_alarmu(client, forester, alarms):
    r = await client.get("/api/v1/alarms", headers=forester)
    by_id = {a["id"]: a for a in r.json()}
    new = by_id[alarms["new"]]
    assert new["sensor"] == {"id": DABROWA_SENSOR, "name": "Skład 5", "lat": 50.06, "lon": 20.31}
    assert new["event_type"] == "theft"
    assert new["status"] == "new"
    assert new["response"] is None
    assert new["possible_tampering"] is False
    assert new["repeats"] == 3
    assert datetime.fromisoformat(new["detected_at"]).tzinfo is not None

    false = by_id[alarms["false"]]
    assert false["possible_tampering"] is True
    assert false["response"]["by"] == "blazej"
    assert false["response"]["comment"] == "zwierzę przy stosie"
    assert false["response"]["lat"] == 50.0601


async def test_nieznany_rodzaj_zdarzenia(client, admin, alarms):
    r = await client.get(f"/api/v1/alarms/{alarms['olszyny']}", headers=admin)
    assert r.json()["event_type"] == "unknown"


async def test_filtry(client, admin, alarms):
    assert await _ids(client, admin, status="new") == [alarms["new"], alarms["olszyny"]]
    assert await _ids(client, admin, sensor_id="70-b3-d5-7e-d0-00-00-02") == [alarms["olszyny"]]
    since = (NOW - timedelta(days=3)).isoformat()
    until = (NOW - timedelta(hours=1)).isoformat()
    assert await _ids(client, admin, **{"from": since, "to": until}) == [alarms["false"]]


async def test_filtr_czasu_bez_strefy_to_utc(client, admin, alarms):
    since = (NOW - timedelta(minutes=20)).replace(tzinfo=None).isoformat()
    assert await _ids(client, admin, **{"from": since}) == [alarms["new"]]


async def test_stronicowanie(client, admin, alarms):
    first = await _ids(client, admin, limit=2)
    second = await _ids(client, admin, limit=2, offset=2)
    assert len(first) == len(second) == 2
    assert not set(first) & set(second)


@pytest.mark.parametrize("params", [{"status": "zly"}, {"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_zle_parametry_422(client, admin, alarms, params):
    r = await client.get("/api/v1/alarms", headers=admin, params=params)
    assert r.status_code == 422


async def test_lesniczy_nie_obejdzie_zakresu_filtrem(client, forester):
    assert await _ids(client, forester, sensor_id=OLSZYNY_SENSOR) == []


# --- GET /alarms/{id} ---


async def test_szczegoly(client, forester, alarms):
    r = await client.get(f"/api/v1/alarms/{alarms['new']}", headers=forester)
    assert r.status_code == 200
    assert r.json()["id"] == alarms["new"]


async def test_szczegoly_404_i_403(client, forester, alarms):
    assert (await client.get("/api/v1/alarms/9999", headers=forester)).status_code == 404
    r = await client.get(f"/api/v1/alarms/{alarms['olszyny']}", headers=forester)
    assert r.status_code == 403


# --- POST /alarms/{id}/response ---


async def _respond(client, headers, alarm_id, **body):
    body.setdefault("result", "theft")
    return await client.post(f"/api/v1/alarms/{alarm_id}/response", headers=headers, json=body)


async def test_odpowiedz_lesniczego(client, forester, alarms):
    r = await _respond(
        client, forester, alarms["new"], result="theft", comment="5 kłód za dużo", lat=50.0601, lon=20.3102
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "theft"
    assert body["response"]["by"] == "blazej"
    assert body["response"]["comment"] == "5 kłód za dużo"
    assert (body["response"]["lat"], body["response"]["lon"]) == (50.0601, 20.3102)
    response_at = datetime.fromisoformat(body["response"]["at"])
    assert abs(response_at - datetime.now(UTC)) < timedelta(minutes=1)


async def test_odpowiedz_bez_komentarza_i_pozycji(client, forester, alarms):
    r = await _respond(client, forester, alarms["new"], result="false_alarm")
    assert r.status_code == 200
    assert r.json()["response"]["lat"] is None


async def test_druga_odpowiedz_409(client, forester, alarms):
    assert (await _respond(client, forester, alarms["new"])).status_code == 200
    assert (await _respond(client, forester, alarms["new"], result="false_alarm")).status_code == 409
    # stara odpowiedź (zapisana w fixture) też jest chroniona
    assert (await _respond(client, forester, alarms["false"])).status_code == 409


async def test_po_odpowiedzi_czujnik_wraca_do_ok(client, forester, alarms, session_maker):
    async with session_maker() as s:
        sensor = await s.get(Sensor, DABROWA_SENSOR)
        sensor.last_seen = NOW
        await s.commit()

    async def state():
        r = await client.get(f"/api/v1/sensors/{DABROWA_SENSOR}", headers=forester)
        return r.json()["state"], r.json()["open_alarm_id"]

    assert await state() == ("alarm", alarms["new"])
    await _respond(client, forester, alarms["new"])
    assert await state() == ("ok", None)


async def test_kto_moze_odpowiedziec(client, forester, manager, admin, alarms):
    assert (await _respond(client, manager, alarms["new"])).status_code == 403
    assert (await _respond(client, forester, alarms["olszyny"])).status_code == 403
    r = await _respond(client, admin, alarms["olszyny"])
    assert r.status_code == 200
    assert r.json()["response"]["by"] == "admin"


async def test_odpowiedz_404(client, forester):
    assert (await _respond(client, forester, 9999)).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"result": "zlapany"},
        {"result": "theft", "lat": 50.0},
        {"result": "theft", "lat": 91, "lon": 20},
        {"result": "theft", "lat": 50, "lon": 181},
        {"result": "theft", "comment": "x" * 501},
    ],
)
async def test_zle_dane_odpowiedzi_422(client, forester, alarms, body):
    r = await client.post(f"/api/v1/alarms/{alarms['new']}/response", headers=forester, json=body)
    assert r.status_code == 422


# --- współpraca z /ingest ---


async def test_alarm_z_ingest_na_liscie(client, admin, alarms):
    r = await client.post(
        "/api/v1/ingest", json={"device": OLSZYNY_SENSOR, "payload_hex": "11002A0101570028B440"}
    )
    # Olszyny mają już otwarty alarm sprzed 30 min: poza oknem scalania (10 min), więc nowy
    assert r.json()["alarm_created"] is True
    newest = (await client.get("/api/v1/alarms", headers=admin, params={"limit": 1})).json()[0]
    assert newest["id"] == r.json()["alarm_id"]
    assert newest["sources"] == ["microphone"]
    assert newest["confidence"] == 87
