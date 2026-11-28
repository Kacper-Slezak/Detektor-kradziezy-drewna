"""Montaż czujnika (PUT /sensors/{id}/mount) i wydania drewna (api.md, sekcje 2 i 3)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Range, Release, Sensor
from tests.utils import auth

NOW = datetime.now(UTC)
UNMOUNTED = "70B3D57ED0000101"
MOUNTED = "70B3D57ED0000102"
OTHER = "70B3D57ED0000103"
ALARM_FRAME = "11002A0101570028B440"


@pytest.fixture
async def ranges(session_maker) -> tuple[int, int]:
    async with session_maker() as s:
        dabrowa, olszyny = (
            Range(name="Leśnictwo Dąbrowa"),
            Range(name="Leśnictwo Olszyny"),
        )
        s.add_all([dabrowa, olszyny])
        await s.flush()
        s.add_all(
            [
                Sensor(id=UNMOUNTED, range_id=dabrowa.id, active=False),
                Sensor(
                    id=MOUNTED,
                    name="Skład 5",
                    range_id=dabrowa.id,
                    lat=50.06,
                    lon=20.31,
                    active=True,
                    last_seen=NOW,
                ),
                Sensor(
                    id=OTHER, range_id=olszyny.id, lat=50.04, lon=20.41, active=True
                ),
            ]
        )
        await s.commit()
        return dabrowa.id, olszyny.id


@pytest.fixture
async def forester(client, make_user, ranges):
    await make_user("blazej", role="forester", range_id=ranges[0])
    return await auth(client, "blazej")


@pytest.fixture
async def manager(client, make_user, ranges):
    await make_user("bogdan", role="district_manager")
    return await auth(client, "bogdan")


async def _sensor(client, headers, sensor_id) -> dict:
    r = await client.get(f"/api/v1/sensors/{sensor_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- montaż ---

MOUNT = {"name": "Skład przy drodze 5", "lat": 50.0647, "lon": 20.3105}


async def test_montaz(client, forester):
    before = await client.get(
        "/api/v1/sensors", headers=forester, params={"unmounted": "true"}
    )
    assert [s["id"] for s in before.json()] == [UNMOUNTED]

    r = await client.put(
        f"/api/v1/sensors/{UNMOUNTED}/mount", headers=forester, json=MOUNT
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["name"], body["lat"], body["lon"]) == (MOUNT["name"], 50.0647, 20.3105)
    assert body["active"] is True
    # jeszcze nic nie wysłał, więc milczy (a nie "inactive")
    assert body["state"] == "silent"

    after = await client.get(
        "/api/v1/sensors", headers=forester, params={"unmounted": "true"}
    )
    assert after.json() == []


async def test_ponowny_montaz_przenosi(client, forester):
    r = await client.put(
        f"/api/v1/sensors/{MOUNTED}/mount",
        headers=forester,
        json={"name": "  Nowe miejsce  ", "lat": 50.1, "lon": 20.2},
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["lat"]) == ("Nowe miejsce", 50.1)
    assert r.json()["state"] == "ok"


async def test_montaz_wlacza_wylaczony(client, forester, admin):
    await client.patch(
        f"/api/v1/sensors/{MOUNTED}", headers=admin, json={"active": False}
    )
    r = await client.put(
        f"/api/v1/sensors/{MOUNTED}/mount", headers=forester, json=MOUNT
    )
    assert r.json()["active"] is True


async def test_montaz_id_z_naklejki(client, forester):
    r = await client.put(
        "/api/v1/sensors/70-b3-d5-7e-d0-00-01-01/mount", headers=forester, json=MOUNT
    )
    assert r.status_code == 200
    assert r.json()["id"] == UNMOUNTED


async def test_kto_montuje(client, forester, manager, admin):
    assert (
        await client.put(f"/api/v1/sensors/{OTHER}/mount", headers=forester, json=MOUNT)
    ).status_code == 403
    assert (
        await client.put(
            f"/api/v1/sensors/{UNMOUNTED}/mount", headers=manager, json=MOUNT
        )
    ).status_code == 403
    assert (
        await client.put(f"/api/v1/sensors/{OTHER}/mount", headers=admin, json=MOUNT)
    ).status_code == 200
    assert (
        await client.put(
            "/api/v1/sensors/FFFFFFFFFFFFFFFF/mount", headers=admin, json=MOUNT
        )
    ).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "lat": 91, "lon": 20},
        {"name": "x", "lat": 50, "lon": -181},
        {"name": "   ", "lat": 50, "lon": 20},
        {"name": "x" * 101, "lat": 50, "lon": 20},
        {"lat": 50, "lon": 20},
        {"name": "x", "lat": 50},
    ],
)
async def test_montaz_zle_dane_422(client, forester, body):
    r = await client.put(
        f"/api/v1/sensors/{UNMOUNTED}/mount", headers=forester, json=body
    )
    assert r.status_code == 422


async def test_po_montazu_alarmy_dzialaja(client, forester):
    # niezamontowany = wyłączony, więc alarm jest pomijany
    r = await client.post(
        "/api/v1/ingest", json={"device": UNMOUNTED, "payload_hex": ALARM_FRAME}
    )
    assert r.json()["muted"] is True
    await client.put(f"/api/v1/sensors/{UNMOUNTED}/mount", headers=forester, json=MOUNT)
    r = await client.post(
        "/api/v1/ingest",
        json={"device": UNMOUNTED, "payload_hex": "11002B0101570028B440"},
    )
    assert r.json()["alarm_created"] is True


# --- wydania: tworzenie ---


async def _release(client, headers, sensor_id=MOUNTED, **body):
    return await client.post(
        f"/api/v1/sensors/{sensor_id}/releases", headers=headers, json=body
    )


async def test_wydanie_domyslne_4h(client, forester):
    r = await _release(
        client, forester, carrier="TransLas", log_count=40, comment="umowa 12/2026"
    )
    assert r.status_code == 201, r.text
    body = r.json()
    starts, ends = (
        datetime.fromisoformat(body["starts_at"]),
        datetime.fromisoformat(body["ends_at"]),
    )
    assert abs(starts - datetime.now(UTC)) < timedelta(minutes=1)
    assert abs((ends - starts) - timedelta(hours=4)) < timedelta(seconds=5)
    assert body["active"] is True
    assert body["created_by"] == "blazej"
    assert body["sensor_name"] == "Skład 5"
    assert (body["carrier"], body["log_count"], body["comment"]) == (
        "TransLas",
        40,
        "umowa 12/2026",
    )

    sensor = await _sensor(client, forester, MOUNTED)
    assert sensor["state"] == "muted"
    assert datetime.fromisoformat(sensor["muted_until"]) == ends


async def test_wydanie_z_koncem_z_apki(client, forester):
    ends = (datetime.now(UTC) + timedelta(hours=1)).replace(microsecond=0)
    r = await _release(client, forester, ends_at=ends.isoformat())
    assert r.status_code == 201
    assert datetime.fromisoformat(r.json()["ends_at"]) == ends


async def test_koniec_bez_strefy_to_utc(client, forester):
    ends = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0, tzinfo=None)
    r = await _release(client, forester, ends_at=ends.isoformat())
    assert datetime.fromisoformat(r.json()["ends_at"]) == ends.replace(tzinfo=UTC)


@pytest.mark.parametrize("delta", [timedelta(minutes=-1), timedelta(hours=25)])
async def test_zly_koniec_422(client, forester, delta):
    r = await _release(
        client, forester, ends_at=(datetime.now(UTC) + delta).isoformat()
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"log_count": -1},
        {"carrier": "x" * 101},
        {"comment": "x" * 501},
        {"ends_at": "jutro"},
    ],
)
async def test_zle_pola_422(client, forester, body):
    assert (await _release(client, forester, **body)).status_code == 422


async def test_trwajace_wydanie_409(client, forester):
    first = await _release(client, forester)
    r = await _release(client, forester)
    assert r.status_code == 409
    assert str(first.json()["id"]) in r.json()["detail"]


async def test_wydanie_niezamontowanego_409(client, forester):
    r = await _release(client, forester, UNMOUNTED)
    assert r.status_code == 409
    assert "zamontowany" in r.json()["detail"]

    await client.put(f"/api/v1/sensors/{UNMOUNTED}/mount", headers=forester, json=MOUNT)
    assert (await _release(client, forester, UNMOUNTED)).status_code == 201


async def test_kto_wydaje(client, forester, manager, admin):
    assert (await _release(client, forester, OTHER)).status_code == 403
    assert (await _release(client, manager)).status_code == 403
    assert (await _release(client, admin, OTHER)).status_code == 201
    assert (await _release(client, admin, "FFFFFFFFFFFFFFFF")).status_code == 404


async def test_wydanie_wycisza_alarmy(client, forester):
    await _release(client, forester)
    r = await client.post(
        "/api/v1/ingest", json={"device": MOUNTED, "payload_hex": ALARM_FRAME}
    )
    assert r.status_code == 201
    assert r.json()["muted"] is True
    assert r.json()["alarm_id"] is None


# --- wydania: zakończenie ---


async def test_zakonczenie_przywraca_alarmy(client, forester):
    release = (await _release(client, forester)).json()
    r = await client.post(f"/api/v1/releases/{release['id']}/end", headers=forester)
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    assert datetime.fromisoformat(r.json()["ends_at"]) <= datetime.now(UTC)

    assert (await _sensor(client, forester, MOUNTED))["state"] == "ok"
    r = await client.post(
        "/api/v1/ingest", json={"device": MOUNTED, "payload_hex": ALARM_FRAME}
    )
    assert r.json()["alarm_created"] is True

    # po zakończeniu można od razu wydać ponownie
    assert (await _release(client, forester)).status_code == 201


async def test_ponowne_zakonczenie_409(client, forester):
    release = (await _release(client, forester)).json()
    await client.post(f"/api/v1/releases/{release['id']}/end", headers=forester)
    r = await client.post(f"/api/v1/releases/{release['id']}/end", headers=forester)
    assert r.status_code == 409


async def test_kto_konczy(client, forester, manager, admin):
    other = (await _release(client, admin, OTHER)).json()
    own = (await _release(client, forester)).json()
    assert (
        await client.post(f"/api/v1/releases/{other['id']}/end", headers=forester)
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/releases/{own['id']}/end", headers=manager)
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/releases/{other['id']}/end", headers=admin)
    ).status_code == 200
    assert (
        await client.post("/api/v1/releases/9999/end", headers=admin)
    ).status_code == 404


# --- wydania: historia ---


@pytest.fixture
async def history(session_maker, ranges) -> dict[str, int]:
    """Dąbrowa: zakończone 3 dni temu, zakończone wczoraj, trwające. Olszyny: zakończone wczoraj."""
    rows = {
        "old": Release(
            sensor_id=MOUNTED,
            starts_at=NOW - timedelta(days=3, hours=4),
            ends_at=NOW - timedelta(days=3),
            carrier="Drewbud",
            created_by="blazej",
        ),
        "yesterday": Release(
            sensor_id=MOUNTED,
            starts_at=NOW - timedelta(days=1, hours=4),
            ends_at=NOW - timedelta(days=1),
            created_by="blazej",
        ),
        "now": Release(
            sensor_id=MOUNTED,
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(hours=3),
            created_by="blazej",
        ),
        "other": Release(
            sensor_id=OTHER,
            starts_at=NOW - timedelta(days=1, hours=2),
            ends_at=NOW - timedelta(days=1),
            created_by="ola",
        ),
    }
    async with session_maker() as s:
        s.add_all(rows.values())
        await s.commit()
        return {k: r.id for k, r in rows.items()}


async def _ids(client, headers, **params) -> list[int]:
    r = await client.get("/api/v1/releases", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return [x["id"] for x in r.json()]


async def test_historia_zakres_i_kolejnosc(client, forester, manager, history):
    assert await _ids(client, forester) == [
        history["now"],
        history["yesterday"],
        history["old"],
    ]
    assert await _ids(client, manager) == [
        history["now"],
        history["other"],
        history["yesterday"],
        history["old"],
    ]


async def test_historia_filtry(client, manager, history):
    assert await _ids(client, manager, active="true") == [history["now"]]
    assert history["now"] not in await _ids(client, manager, active="false")
    assert await _ids(client, manager, sensor_id="70b3d57ed0000103") == [
        history["other"]
    ]
    since = (NOW - timedelta(days=2)).isoformat()
    until = (NOW - timedelta(hours=12)).isoformat()
    assert await _ids(client, manager, **{"from": since, "to": until}) == [
        history["other"],
        history["yesterday"],
    ]
    assert len(await _ids(client, manager, limit=2)) == 2


async def test_historia_ksztalt(client, forester, history):
    r = await client.get(
        "/api/v1/releases", headers=forester, params={"active": "true"}
    )
    item = r.json()[0]
    assert set(item) == {
        "id",
        "sensor_id",
        "sensor_name",
        "starts_at",
        "ends_at",
        "active",
        "carrier",
        "log_count",
        "comment",
        "created_by",
    }
    assert item["active"] is True


async def test_historia_wymaga_logowania(client):
    assert (await client.get("/api/v1/releases")).status_code == 401


async def test_lesniczy_bez_lesnictwa_nie_widzi_wydan(client, make_user, history):
    await make_user("bez", role="forester")
    assert await _ids(client, await auth(client, "bez")) == []
