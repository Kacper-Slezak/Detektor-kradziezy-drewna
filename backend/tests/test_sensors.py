"""Endpointy czujników i wyliczanie stanu (api.md, sekcja 2)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Alarm, Range, Release, Sensor
from app.services.sensors import compute_state
from tests.conftest import SENSOR_ID
from tests.utils import auth

NOW = datetime.now(UTC)
RECENT = NOW - timedelta(minutes=5)

# ID czujników w danych testowych
OK = "70B3D57ED0000001"
ALARM = "70B3D57ED0000002"
MUTED = "70B3D57ED0000003"
SILENT = "70B3D57ED0000004"
OFF = "70B3D57ED0000005"
UNMOUNTED = "70B3D57ED0000006"
OTHER_RANGE = "70B3D57ED0000007"


# --- compute_state bez bazy ---


def _sensor(**kwargs) -> Sensor:
    defaults = {"id": OK, "lat": 50.0, "lon": 20.0, "active": True, "last_seen": RECENT}
    return Sensor(**(defaults | kwargs))


def _state(sensor, alarm=None, muted=None):
    return compute_state(sensor, open_alarm_id=alarm, muted_until=muted, now=NOW)


def test_stan_ok():
    assert _state(_sensor()) == "ok"


def test_stan_wylaczony_i_niezamontowany_to_inactive():
    assert _state(_sensor(active=False)) == "inactive"
    assert _state(_sensor(lat=None, lon=None)) == "inactive"
    # wyłączony wygrywa nawet z otwartym alarmem
    assert _state(_sensor(active=False), alarm=1) == "inactive"


def test_alarm_wygrywa_z_wyciszeniem_i_milczeniem():
    old = NOW - timedelta(days=2)
    assert (
        _state(_sensor(last_seen=old), alarm=1, muted=NOW + timedelta(hours=1))
        == "alarm"
    )


def test_wyciszony_wygrywa_z_milczeniem():
    old = NOW - timedelta(days=2)
    assert _state(_sensor(last_seen=old), muted=NOW + timedelta(hours=1)) == "muted"


def test_milczy_po_12_h_albo_gdy_nigdy_nie_nadawal():
    assert _state(_sensor(last_seen=NOW - timedelta(hours=11, minutes=59))) == "ok"
    assert _state(_sensor(last_seen=NOW - timedelta(hours=12, minutes=1))) == "silent"
    assert _state(_sensor(last_seen=None)) == "silent"


def test_czas_bez_strefy_z_sqlite_traktowany_jako_utc():
    naive = (NOW - timedelta(minutes=1)).replace(tzinfo=None)
    assert _state(_sensor(last_seen=naive)) == "ok"


# --- dane w bazie ---


@pytest.fixture
async def ranges(session_maker) -> tuple[int, int]:
    """Dwa leśnictwa i czujnik w każdym stanie."""
    async with session_maker() as s:
        dabrowa, olszyny = (
            Range(name="Leśnictwo Dąbrowa"),
            Range(name="Leśnictwo Olszyny"),
        )
        s.add_all([dabrowa, olszyny])
        await s.flush()
        d, o = dabrowa.id, olszyny.id
        mounted = {
            "lat": 50.05,
            "lon": 20.35,
            "active": True,
            "last_seen": RECENT,
            "battery_pct": 80,
        }
        s.add_all(
            [
                Sensor(id=OK, name="Skład przy drodze 5", range_id=d, **mounted),
                Sensor(id=ALARM, name="Skład przy szlabanie", range_id=d, **mounted),
                Sensor(id=MUTED, name="Skład przy stawie", range_id=d, **mounted),
                Sensor(
                    id=SILENT,
                    range_id=d,
                    **(mounted | {"last_seen": NOW - timedelta(hours=20)}),
                ),
                Sensor(id=OFF, range_id=d, **(mounted | {"active": False})),
                Sensor(id=UNMOUNTED, range_id=d, active=False),
                Sensor(id=OTHER_RANGE, range_id=o, **mounted),
            ]
        )
        await s.flush()
        alarm = {
            "started_at": RECENT, "last_frame_at": RECENT, "event_type": 1, "sources": ["microphone"],
            "confidence": 87, "duration_s": 40, "energy": 180,
        }  # fmt: skip
        s.add_all(
            [
                Alarm(sensor_id=ALARM, **alarm),
                # alarm z odpowiedzią nie zmienia stanu
                Alarm(sensor_id=OK, status="false_alarm", **alarm),
                Release(
                    sensor_id=MUTED,
                    starts_at=NOW - timedelta(hours=1),
                    ends_at=NOW + timedelta(hours=3),
                    carrier="TransLas",
                    log_count=40,
                ),
                # zakończone wydanie nie wycisza
                Release(
                    sensor_id=OK,
                    starts_at=NOW - timedelta(days=1),
                    ends_at=NOW - timedelta(hours=20),
                ),
            ]
        )
        await s.commit()
        return d, o


@pytest.fixture
async def forester(client, make_user, ranges):
    await make_user("blazej", role="forester", range_id=ranges[0])
    return await auth(client, "blazej")


@pytest.fixture
async def manager(client, make_user, ranges):
    await make_user("bogdan", role="district_manager")
    return await auth(client, "bogdan")


async def _list(client, headers, **params) -> dict[str, dict]:
    r = await client.get("/api/v1/sensors", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return {s["id"]: s for s in r.json()}


# --- GET /sensors ---


async def test_lista_wymaga_logowania(client):
    r = await client.get("/api/v1/sensors")
    assert r.status_code == 401


async def test_lesniczy_widzi_tylko_swoje_lesnictwo(client, forester):
    sensors = await _list(client, forester)
    assert OTHER_RANGE not in sensors
    assert SENSOR_ID not in sensors  # czujnik z conftest nie ma leśnictwa
    assert len(sensors) == 6


async def test_lesniczy_bez_lesnictwa_nie_widzi_nic(client, make_user, ranges):
    await make_user("bez", role="forester")
    assert await _list(client, await auth(client, "bez")) == {}


async def test_nadlesniczy_i_admin_widza_wszystko(client, manager, admin, ranges):
    assert len(await _list(client, manager)) == 8
    assert len(await _list(client, admin)) == 8


async def test_stany_na_liscie(client, forester):
    sensors = await _list(client, forester)
    assert {i: s["state"] for i, s in sensors.items()} == {
        OK: "ok",
        ALARM: "alarm",
        MUTED: "muted",
        SILENT: "silent",
        OFF: "inactive",
        UNMOUNTED: "inactive",
    }
    assert sensors[ALARM]["open_alarm_id"] is not None
    assert sensors[OK]["open_alarm_id"] is None
    assert sensors[MUTED]["muted_until"] is not None
    assert sensors[OK]["muted_until"] is None


async def test_ksztalt_odpowiedzi(client, forester, ranges):
    sensor = (await _list(client, forester))[OK]
    assert set(sensor) == {
        "id", "name", "lat", "lon", "range_id", "active", "state",
        "battery_pct", "last_seen", "muted_until", "open_alarm_id",
    }  # fmt: skip
    assert sensor["range_id"] == ranges[0]
    assert sensor["battery_pct"] == 80
    assert datetime.fromisoformat(sensor["last_seen"]).tzinfo is not None


async def test_filtry(client, admin, ranges):
    assert set(await _list(client, admin, state="alarm")) == {ALARM}
    assert set(await _list(client, admin, range_id=ranges[1])) == {OTHER_RANGE}
    assert set(await _list(client, admin, unmounted="true", range_id=ranges[0])) == {
        UNMOUNTED
    }


async def test_zly_stan_w_filtrze(client, admin):
    r = await client.get("/api/v1/sensors", headers=admin, params={"state": "zepsuty"})
    assert r.status_code == 422


async def test_lesniczy_nie_obejdzie_zakresu_filtrem(client, forester, ranges):
    assert await _list(client, forester, range_id=ranges[1]) == {}


# --- GET /sensors/{id} ---


async def test_szczegoly_z_ostatnimi_alarmami_i_wydaniami(client, forester):
    r = await client.get(f"/api/v1/sensors/{OK}", headers=forester)
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ok"
    assert [a["status"] for a in body["recent_alarms"]] == ["false_alarm"]
    assert set(body["recent_alarms"][0]) == {
        "id",
        "detected_at",
        "status",
        "confidence",
    }
    assert len(body["recent_releases"]) == 1


async def test_szczegoly_id_male_litery_i_separatory(client, admin, ranges):
    r = await client.get("/api/v1/sensors/70-b3-d5-7e-d0-00-00-03", headers=admin)
    assert r.status_code == 200
    assert r.json()["recent_releases"][0]["carrier"] == "TransLas"


async def test_szczegoly_404_i_403(client, forester):
    r = await client.get("/api/v1/sensors/FFFFFFFFFFFFFFFF", headers=forester)
    assert r.status_code == 404
    r = await client.get(f"/api/v1/sensors/{OTHER_RANGE}", headers=forester)
    assert r.status_code == 403


# --- POST /sensors ---


async def test_admin_dodaje_czujnik(client, admin, ranges):
    r = await client.post(
        "/api/v1/sensors",
        headers=admin,
        json={
            "id": "70 b3 d5 7e d0 05 99 99",
            "range_id": ranges[1],
            "name": "Nowy skład",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == "70B3D57ED0059999"
    assert body["active"] is False
    assert body["state"] == "inactive"
    assert body["lat"] is None

    unmounted = await _list(client, admin, unmounted="true", range_id=ranges[1])
    assert "70B3D57ED0059999" in unmounted


async def test_dodanie_bez_nazwy(client, admin, ranges):
    r = await client.post(
        "/api/v1/sensors",
        headers=admin,
        json={"id": "70B3D57ED0059998", "range_id": ranges[0]},
    )
    assert r.status_code == 201
    assert r.json()["name"] is None


async def test_dodanie_duplikatu_409(client, admin, ranges):
    r = await client.post(
        "/api/v1/sensors", headers=admin, json={"id": OK.lower(), "range_id": ranges[0]}
    )
    assert r.status_code == 409


@pytest.mark.parametrize(
    "bad_id", ["70B3D57ED005", "70B3D57ED00512345", "70B3D57ED005123G", ""]
)
async def test_zle_id_422(client, admin, ranges, bad_id):
    r = await client.post(
        "/api/v1/sensors", headers=admin, json={"id": bad_id, "range_id": ranges[0]}
    )
    assert r.status_code == 422


async def test_dodanie_do_nieistniejacego_lesnictwa_400(client, admin):
    r = await client.post(
        "/api/v1/sensors",
        headers=admin,
        json={"id": "70B3D57ED0059997", "range_id": 999},
    )
    assert r.status_code == 400


async def test_dodaje_tylko_admin(client, forester, manager, ranges):
    body = {"id": "70B3D57ED0059996", "range_id": ranges[0]}
    for headers in (forester, manager):
        r = await client.post("/api/v1/sensors", headers=headers, json=body)
        assert r.status_code == 403


# --- PATCH /sensors/{id} ---


async def test_admin_zmienia_lesnictwo_i_nazwe(client, admin, ranges):
    r = await client.patch(
        f"/api/v1/sensors/{OK}",
        headers=admin,
        json={"range_id": ranges[1], "name": "Przeniesiony"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["range_id"] == ranges[1]
    assert r.json()["name"] == "Przeniesiony"
    assert r.json()["state"] == "ok"


async def test_lesniczy_zmienia_nazwe_i_wylacza_swoj(client, forester):
    r = await client.patch(
        f"/api/v1/sensors/{OK}", headers=forester, json={"name": "Skład 5 (nowy)"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Skład 5 (nowy)"

    r = await client.patch(
        f"/api/v1/sensors/{OK}", headers=forester, json={"active": False}
    )
    assert r.json()["state"] == "inactive"


async def test_name_null_usuwa_nazwe(client, admin, ranges):
    r = await client.patch(f"/api/v1/sensors/{OK}", headers=admin, json={"name": None})
    assert r.status_code == 200
    assert r.json()["name"] is None


async def test_puste_body_nic_nie_zmienia(client, admin, ranges):
    r = await client.patch(f"/api/v1/sensors/{OK}", headers=admin, json={})
    assert r.status_code == 200
    assert r.json()["name"] == "Skład przy drodze 5"


async def test_lesniczy_nie_zmienia_lesnictwa(client, forester, ranges):
    r = await client.patch(
        f"/api/v1/sensors/{OK}", headers=forester, json={"range_id": ranges[1]}
    )
    assert r.status_code == 403


async def test_lesniczy_nie_rusza_cudzego(client, forester):
    r = await client.patch(
        f"/api/v1/sensors/{OTHER_RANGE}", headers=forester, json={"name": "x"}
    )
    assert r.status_code == 403


async def test_nadlesniczy_tylko_czyta(client, manager):
    r = await client.patch(f"/api/v1/sensors/{OK}", headers=manager, json={"name": "x"})
    assert r.status_code == 403


@pytest.mark.parametrize("body", [{"range_id": None}, {"active": None}, {"name": ""}])
async def test_zle_wartosci_422(client, admin, ranges, body):
    r = await client.patch(f"/api/v1/sensors/{OK}", headers=admin, json=body)
    assert r.status_code == 422


async def test_patch_nieistniejace_lesnictwo_400_i_brak_czujnika_404(
    client, admin, ranges
):
    r = await client.patch(
        f"/api/v1/sensors/{OK}", headers=admin, json={"range_id": 999}
    )
    assert r.status_code == 400
    r = await client.patch(
        "/api/v1/sensors/FFFFFFFFFFFFFFFF", headers=admin, json={"name": "x"}
    )
    assert r.status_code == 404


# --- współpraca z /ingest ---


async def test_alarm_z_ingest_widoczny_na_liscie(client, admin, ranges):
    # 11 00 2A ... = ALARM z protokołu
    r = await client.post(
        "/api/v1/ingest", json={"device": OK, "payload_hex": "11002A0101570028B440"}
    )
    assert r.status_code == 201, r.text
    sensor = (await _list(client, admin))[OK]
    assert sensor["state"] == "alarm"
    assert sensor["open_alarm_id"] == r.json()["alarm_id"]
    assert sensor["battery_pct"] == 64


async def test_lesniczy_bez_lesnictwa_nie_otworzy_czujnika_bez_lesnictwa(
    client, make_user, ranges
):
    await make_user("bez", role="forester")
    r = await client.get(
        f"/api/v1/sensors/{SENSOR_ID}", headers=await auth(client, "bez")
    )
    assert r.status_code == 403
