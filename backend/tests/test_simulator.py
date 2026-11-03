"""Symulator wysyła ramki przez prawdziwe /ingest (ASGI w pamięci, bez sieci)."""

import json
import logging

import pytest
from sqlalchemy import select

from app.demo import DEMO_SENSORS
from app.models import Alarm, Message, Sensor
from tests.conftest import SENSOR_ID
from tools.simulator import DEFAULT_SENSORS, VirtualSensor, load_state, parse_args, run

SECOND = "70B3D57ED0005678"


@pytest.fixture
async def two_sensors(session_maker):
    async with session_maker() as s:
        s.add(Sensor(id=SECOND, name="Drugi", lat=50.0, lon=20.0))
        await s.commit()


async def _run(client, tmp_path, *extra):
    args = parse_args(
        [
            "--sensors",
            f"{SENSOR_ID},{SECOND}",
            "--once",
            "--repeat-gap",
            "0",
            "--seed",
            "1",
            "--state",
            str(tmp_path / "state.json"),
            *extra,
        ]
    )
    await run(args, client)
    return args


async def _messages(session_maker, sensor_id) -> list[Message]:
    async with session_maker() as s:
        q = select(Message).where(Message.sensor_id == sensor_id).order_by(Message.id)
        return list(await s.scalars(q))


async def test_normal_boot_i_heartbeat(client, session_maker, two_sensors, tmp_path):
    await _run(client, tmp_path, "--alarm-chance", "0")
    for sensor_id in (SENSOR_ID, SECOND):
        assert [m.msg_type for m in await _messages(session_maker, sensor_id)] == [
            "BOOT",
            "HEARTBEAT",
        ]
    async with session_maker() as s:
        sensor = await s.get(Sensor, SENSOR_ID)
        assert sensor.last_counter == 2
        assert sensor.battery_pct == 95


async def test_theft_daje_jeden_alarm_z_trzech_ramek(
    client, session_maker, two_sensors, tmp_path
):
    await _run(client, tmp_path, "--scenario", "theft", "--target", SECOND)
    async with session_maker() as s:
        alarms = list(await s.scalars(select(Alarm)))
    assert len(alarms) == 1
    assert alarms[0].sensor_id == SECOND
    assert alarms[0].repeats == 3
    assert alarms[0].sources == ["microphone", "vibration"]


async def test_false_alarm_same_wibracje(client, session_maker, two_sensors, tmp_path):
    await _run(client, tmp_path, "--scenario", "false-alarm")
    async with session_maker() as s:
        alarm = await s.scalar(select(Alarm))
    assert alarm.sources == ["vibration"]
    assert alarm.confidence <= 60


async def test_duplicate_backend_odrzuca_drugi_raz(
    client, session_maker, two_sensors, tmp_path, caplog
):
    with caplog.at_level(logging.INFO, logger="simulator"):
        await _run(client, tmp_path, "--scenario", "duplicate", "--alarm-chance", "0")
    assert "duplicate" in caplog.text
    # heartbeat zapisany tylko raz (BOOT backend zawsze przyjmuje, patrz is_duplicate)
    types = [m.msg_type for m in await _messages(session_maker, SENSOR_ID)]
    assert types.count("HEARTBEAT") == 1


async def test_battery_drain(client, session_maker, two_sensors, tmp_path):
    await _run(client, tmp_path, "--scenario", "battery-drain", "--target", SENSOR_ID)
    async with session_maker() as s:
        assert (await s.get(Sensor, SENSOR_ID)).battery_pct == 90
        assert (await s.get(Sensor, SECOND)).battery_pct == 95


async def test_silent_wysyla_tylko_boot(client, session_maker, two_sensors, tmp_path):
    await _run(client, tmp_path, "--scenario", "silent", "--target", SENSOR_ID)
    assert [m.msg_type for m in await _messages(session_maker, SENSOR_ID)] == ["BOOT"]
    assert len(await _messages(session_maker, SECOND)) == 2


async def test_licznik_przetrwa_restart(client, session_maker, two_sensors, tmp_path):
    await _run(client, tmp_path, "--alarm-chance", "0")
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved[SENSOR_ID]["counter"] == 2

    await _run(client, tmp_path, "--alarm-chance", "0")
    counters = [m.counter for m in await _messages(session_maker, SENSOR_ID)]
    assert counters == [1, 2, 3, 4]  # po restarcie BOOT z licznikiem 3, nie od zera


async def test_nieznany_czujnik_nie_wywala_symulatora(
    client, session_maker, tmp_path, caplog
):
    args = parse_args(
        ["--sensors", "ffffffffffffffff", "--once", "--state", str(tmp_path / "s.json")]
    )
    assert args.sensors == ["FFFFFFFFFFFFFFFF"]
    with caplog.at_level(logging.ERROR, logger="simulator"):
        await run(args, client)
    assert "nie zna czujnika" in caplog.text


def test_domyslne_czujniki_to_zamontowane_czujniki_demo():
    assert DEFAULT_SENSORS
    assert all(len(i) == 16 for i in DEFAULT_SENSORS)


def test_bateria_czujnikow_demo_z_seeda(tmp_path):
    low = next(s for s in DEMO_SENSORS if s.scenario == "low_battery")
    [sensor] = load_state(tmp_path / "brak.json", [low.id])
    assert sensor.battery < 20


def test_licznik_przekreca_sie():
    sensor = VirtualSensor(id=SENSOR_ID, counter=65535)
    assert sensor.next_counter() == 0
