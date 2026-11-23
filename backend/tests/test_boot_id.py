"""Ochrona przed powtórką BOOT: BOOT wersji 2 niesie boot_id, który tylko rośnie."""

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Alarm, Message, Sensor
from app.protocol.encoder import encode_alarm, encode_boot
from app.services.ingest import is_boot_replay
from tests.conftest import SENSOR_ID
from tests.utils import auth


def boot(counter, boot_id=None) -> str:
    return encode_boot(counter, battery_pct=88, boot_id=boot_id).hex()


def alarm(counter) -> str:
    return encode_alarm(
        counter,
        sources=["microphone"],
        confidence=87,
        duration_s=40,
        energy=180,
        battery_pct=64,
    ).hex()


async def post(client, payload_hex):
    return await client.post(
        "/api/v1/ingest", json={"device": SENSOR_ID, "payload_hex": payload_hex}
    )


async def state(session_maker) -> tuple[int | None, int | None]:
    async with session_maker() as s:
        sensor = await s.get(Sensor, SENSOR_ID)
        return sensor.last_counter, sensor.last_boot_id


async def count(session_maker, model) -> int:
    async with session_maker() as s:
        return await s.scalar(select(func.count()).select_from(model))


# --- reguła ---


@pytest.mark.parametrize(
    "last, new, replay",
    [
        (None, 1, False),  # pierwszy BOOT z boot_id
        (5, 6, False),
        (5, 5, True),  # ten sam = powtórka
        (5, 4, True),  # starszy
        (5, 1000, False),
        (65535, 0, False),  # przekręcenie licznika
        (65535, 1, False),
        (10, 40000, True),  # skok o więcej niż pół zakresu traktujemy jak stary numer
    ],
)
def test_is_boot_replay(last, new, replay):
    assert is_boot_replay(last, new) is replay


# --- ingest ---


async def test_pierwszy_boot_z_boot_id_zapisuje_numer(client, session_maker):
    r = await post(client, boot(1, boot_id=7))
    assert r.status_code == 201 and r.json()["status"] == "stored"
    assert await state(session_maker) == (1, 7)
    async with session_maker() as s:
        message = await s.scalar(select(Message))
    assert message.decoded["boot_id"] == 7


async def test_powtorzony_boot_nie_odblokowuje_starych_ramek(client, session_maker):
    """Dokładnie scenariusz z przeglądu: BOOT, ALARM, powtórka ALARM, powtórka BOOT, powtórka ALARM."""
    assert (await post(client, boot(1, boot_id=1))).status_code == 201
    assert (await post(client, alarm(3))).status_code == 201

    r = await post(client, alarm(3))
    assert r.status_code == 200 and r.json()["status"] == "duplicate"

    r = await post(client, boot(1, boot_id=1))  # atakujący powtarza zapisany BOOT
    assert r.status_code == 200 and r.json()["status"] == "duplicate"
    assert await state(session_maker) == (3, 1)  # licznik NIE został zresetowany

    r = await post(client, alarm(3))  # i stary ALARM dalej jest odrzucany
    assert r.status_code == 200 and r.json()["status"] == "duplicate"
    assert await count(session_maker, Alarm) == 1
    assert (
        await count(session_maker, Message) == 2
    )  # BOOT i ALARM, powtórek nie zapisano


async def test_nowy_boot_resetuje_licznik(client, session_maker):
    await post(client, boot(1, boot_id=1))
    await post(client, alarm(50))
    assert await state(session_maker) == (50, 1)

    assert (await post(client, boot(1, boot_id=2))).status_code == 201  # restart płytki
    assert await state(session_maker) == (1, 2)
    assert (await post(client, alarm(2))).status_code == 201  # licznik zaczął od nowa


async def test_starszy_boot_id_jest_odrzucany(client, session_maker):
    await post(client, boot(1, boot_id=5))
    for boot_id in (5, 4, 1):
        r = await post(client, boot(1, boot_id=boot_id))
        assert r.json()["status"] == "duplicate", boot_id
    assert (await state(session_maker))[1] == 5


async def test_przekrecenie_boot_id(client, session_maker):
    await post(client, boot(1, boot_id=65535))
    assert (await post(client, boot(1, boot_id=0))).status_code == 201
    assert (await state(session_maker))[1] == 0


# --- zgodność wstecz i degradacja ---


async def test_boot_wersji_1_dziala_jak_dotad(client, session_maker):
    assert (await post(client, boot(1))).status_code == 201
    assert (
        await post(client, boot(1))
    ).status_code == 201  # nic nie blokuje, bez boot_id
    assert await state(session_maker) == (1, None)


async def test_boot_bez_boot_id_od_czujnika_z_boot_id_to_422(client, session_maker):
    """Bez tej reguły wystarczyłby stary BOOT wersji 1, żeby zresetować licznik."""
    await post(client, boot(1, boot_id=3))
    await post(client, alarm(9))

    r = await post(client, boot(1))
    assert r.status_code == 422 and "boot_id" in r.json()["detail"]
    assert await state(session_maker) == (9, 3)


async def test_wymagany_boot_id(client, monkeypatch):
    monkeypatch.setattr(settings, "boot_id_required", True)
    r = await post(client, boot(1))
    assert r.status_code == 422 and "boot_id" in r.json()["detail"]
    assert (await post(client, boot(1, boot_id=1))).status_code == 201
    assert (await post(client, alarm(2))).status_code == 201  # inne ramki bez zmian


async def test_alarm_w_ramce_wersji_2(client):
    payload = encode_alarm(
        4,
        sources=["microphone"],
        confidence=87,
        duration_s=40,
        energy=180,
        battery_pct=64,
        version=2,
    ).hex()
    r = await post(client, payload)
    assert r.status_code == 201 and r.json()["alarm_created"] is True


# --- reset przez admina ---


async def test_reset_boot_przyjmuje_nizszy_numer(client, session_maker, make_user):
    await make_user("admin", role="admin")
    await post(client, boot(1, boot_id=500))
    await post(client, alarm(8))
    assert (await post(client, boot(1, boot_id=1))).json()[
        "status"
    ] == "duplicate"  # po wymianie płytki

    r = await client.post(
        f"/api/v1/sensors/{SENSOR_ID}/reset-boot", headers=await auth(client, "admin")
    )
    assert r.status_code == 204
    assert await state(session_maker) == (None, None)

    assert (await post(client, boot(1, boot_id=1))).status_code == 201
    assert await state(session_maker) == (1, 1)


async def test_reset_boot_tylko_admin(client, make_user, session_maker):
    await make_user("blazej", role="forester")
    await make_user("bogdan", role="district_manager")
    await post(client, boot(1, boot_id=5))
    url = f"/api/v1/sensors/{SENSOR_ID}/reset-boot"
    for login in ("blazej", "bogdan"):
        assert (
            await client.post(url, headers=await auth(client, login))
        ).status_code == 403
    assert (await client.post(url)).status_code == 401
    assert await state(session_maker) == (1, 5)


async def test_reset_boot_nieznany_czujnik_404(client, make_user):
    await make_user("admin", role="admin")
    r = await client.post(
        "/api/v1/sensors/FFFFFFFFFFFFFFFF/reset-boot",
        headers=await auth(client, "admin"),
    )
    assert r.status_code == 404
