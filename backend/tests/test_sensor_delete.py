"""DELETE /sensors/{id}: tylko admin i tylko czujnik bez historii (alarmów i wydań)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Alarm, Message, Release, Sensor
from tests.conftest import SENSOR_ID
from tests.utils import auth

OTHER = "70B3D57ED0000002"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
async def admin_headers(client, make_user):
    await make_user("admin", role="admin")
    return await auth(client, "admin")


def message(sensor_id, counter=1) -> Message:
    return Message(
        received_at=NOW,
        sensor_id=sensor_id,
        msg_type="HEARTBEAT",
        counter=counter,
        payload_hex="120001580000",
        decoded={},
        rssi=-100,
    )


def alarm(sensor_id) -> Alarm:
    return Alarm(
        sensor_id=sensor_id,
        started_at=NOW,
        last_frame_at=NOW,
        event_type=1,
        sources=["microphone"],
        confidence=87,
        duration_s=40,
        energy=180,
    )


def release(sensor_id) -> Release:
    return Release(sensor_id=sensor_id, starts_at=NOW, ends_at=NOW + timedelta(hours=4))


async def add(session_maker, *rows):
    async with session_maker() as s:
        s.add_all(rows)
        await s.commit()


async def count(session_maker, model, sensor_id) -> int:
    async with session_maker() as s:
        return await s.scalar(
            select(func.count()).select_from(model).where(model.sensor_id == sensor_id)
        )


async def exists(session_maker, sensor_id) -> bool:
    async with session_maker() as s:
        return await s.get(Sensor, sensor_id) is not None


async def delete(client, headers, sensor_id=SENSOR_ID):
    return await client.delete(f"/api/v1/sensors/{sensor_id}", headers=headers)


async def test_usuniecie_czujnika_bez_historii(client, admin_headers, session_maker):
    r = await delete(client, admin_headers)
    assert r.status_code == 204
    assert not await exists(session_maker, SENSOR_ID)
    assert (
        await client.get(f"/api/v1/sensors/{SENSOR_ID}", headers=admin_headers)
    ).status_code == 404


async def test_surowe_ramki_znikaja_z_czujnikiem_a_cudze_zostaja(
    client, admin_headers, session_maker
):
    await add(session_maker, Sensor(id=OTHER, name="Drugi"))
    await add(
        session_maker, message(SENSOR_ID, 1), message(SENSOR_ID, 2), message(OTHER, 1)
    )

    assert (await delete(client, admin_headers)).status_code == 204
    assert await count(session_maker, Message, SENSOR_ID) == 0
    assert await count(session_maker, Message, OTHER) == 1
    assert await exists(session_maker, OTHER)


@pytest.mark.parametrize("history", [alarm, release])
async def test_czujnik_z_historia_409_i_nic_nie_znika(
    client, admin_headers, session_maker, history
):
    await add(session_maker, message(SENSOR_ID), history(SENSOR_ID))

    r = await delete(client, admin_headers)
    assert r.status_code == 409
    assert (
        "historię" in r.json()["detail"] and "PATCH active=false" in r.json()["detail"]
    )
    assert await exists(session_maker, SENSOR_ID)
    assert await count(session_maker, Message, SENSOR_ID) == 1  # ramki też zostają


async def test_komunikat_409_ma_liczby(client, admin_headers, session_maker):
    await add(session_maker, alarm(SENSOR_ID), alarm(SENSOR_ID), release(SENSOR_ID))
    detail = (await delete(client, admin_headers)).json()["detail"]
    assert "alarmy: 2" in detail and "wydania: 1" in detail


async def test_wylaczony_czujnik_bez_historii_da_sie_usunac(
    client, admin_headers, session_maker
):
    async with session_maker() as s:
        (await s.get(Sensor, SENSOR_ID)).active = False
        await s.commit()
    assert (await delete(client, admin_headers)).status_code == 204


async def test_wylaczenie_czujnika_z_historia_dalej_dziala(
    client, admin_headers, session_maker
):
    """Wyłączenie niczego nie kasuje: historia zostaje, czujnik jest tylko nieaktywny."""
    await add(session_maker, alarm(SENSOR_ID), release(SENSOR_ID), message(SENSOR_ID))
    r = await client.patch(
        f"/api/v1/sensors/{SENSOR_ID}", headers=admin_headers, json={"active": False}
    )
    assert r.status_code == 200 and r.json()["active"] is False
    assert await count(session_maker, Alarm, SENSOR_ID) == 1
    assert await count(session_maker, Release, SENSOR_ID) == 1
    assert await count(session_maker, Message, SENSOR_ID) == 1


async def test_id_jak_z_naklejki(client, admin_headers, session_maker):
    await add(session_maker, Sensor(id=OTHER))
    r = await delete(client, admin_headers, "70:b3:d5:7e:d0:00:00:02")
    assert r.status_code == 204
    assert not await exists(session_maker, OTHER)


async def test_nieznany_czujnik_404(client, admin_headers):
    assert (await delete(client, admin_headers, "FFFFFFFFFFFFFFFF")).status_code == 404


async def test_tylko_admin(client, make_user, session_maker):
    await make_user("blazej", role="forester")
    await make_user("bogdan", role="district_manager")
    for login in ("blazej", "bogdan"):
        assert (await delete(client, await auth(client, login))).status_code == 403
    assert (await client.delete(f"/api/v1/sensors/{SENSOR_ID}")).status_code == 401
    assert await exists(session_maker, SENSOR_ID)
