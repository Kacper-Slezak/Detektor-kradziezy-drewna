"""Symulator wysyła ramki przez prawdziwe /ingest (ASGI w pamięci, bez sieci)."""

import json
import logging

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.demo import DEMO_SENSORS
from app.models import Alarm, Message, Sensor
from tests.conftest import SENSOR_ID
from tools.simulator import (
    DEFAULT_SENSORS,
    Simulator,
    VirtualSensor,
    load_state,
    parse_args,
    run,
    wait_for_api,
)

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


async def test_v3_boot_id_przetrwa_restart_licznik_od_nowa(
    client, session_maker, two_sensors, tmp_path
):
    """Wersja 3: po restarcie nowa sesja (boot_id + 1), licznik znowu od 1, wszystko przyjęte."""
    await _run(client, tmp_path, "--alarm-chance", "0")
    saved = json.loads((tmp_path / "state.json").read_text())
    assert (saved[SENSOR_ID]["boot_id"], saved[SENSOR_ID]["counter"]) == (1, 2)

    await _run(client, tmp_path, "--alarm-chance", "0")
    msgs = await _messages(session_maker, SENSOR_ID)
    assert [(m.decoded["header"]["boot_id"], m.counter) for m in msgs] == [
        (1, 1), (1, 2), (2, 1), (2, 2),
    ]


async def test_v2_licznik_przetrwa_restart(client, session_maker, two_sensors, tmp_path):
    """--frame-version 2 (przejściowo): licznik przetrwa restart, BOOT wersji 2 z boot_id."""
    await _run(client, tmp_path, "--alarm-chance", "0", "--frame-version", "2")
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved[SENSOR_ID]["counter"] == 2

    await _run(client, tmp_path, "--alarm-chance", "0", "--frame-version", "2")
    msgs = await _messages(session_maker, SENSOR_ID)
    assert [m.counter for m in msgs] == [1, 2, 3, 4]  # po restarcie BOOT z licznikiem 3
    assert [m.decoded["header"]["version"] for m in msgs] == [2, 1, 2, 1]


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


def _down(request):
    raise httpx.ConnectError("odmowa połączenia")


async def test_backend_nie_odpowiada_symulator_dziala_dalej(caplog):
    async with httpx.AsyncClient(transport=httpx.MockTransport(_down), base_url="http://x") as c:
        sim = Simulator(c, [VirtualSensor(id=SENSOR_ID)])
        with caplog.at_level(logging.WARNING, logger="simulator"):
            assert await sim.heartbeat(sim.sensors[0]) == []
    assert "nie odpowiada" in caplog.text


async def test_blad_500_podpowiada_migracje(caplog):
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="Internal Server Error"))
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as c:
        sim = Simulator(c, [VirtualSensor(id=SENSOR_ID)])
        with caplog.at_level(logging.ERROR, logger="simulator"):
            await sim.boot(sim.sensors[0])
    assert "alembic upgrade head" in caplog.text


async def test_czekanie_na_backend():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("jeszcze nie")
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x") as c:
        assert await wait_for_api(c, timeout_s=5, step_s=0) is True
        assert len(calls) == 3


async def test_czekanie_konczy_sie_po_czasie():
    async with httpx.AsyncClient(transport=httpx.MockTransport(_down), base_url="http://x") as c:
        assert await wait_for_api(c, timeout_s=0, step_s=0) is False


async def test_boot_id_rosnie_przy_kazdym_uruchomieniu(
    client, session_maker, two_sensors, tmp_path
):
    """Dwa uruchomienia z tym samym plikiem stanu: drugi BOOT ma większy boot_id i jest przyjęty."""
    await _run(client, tmp_path, "--alarm-chance", "0")
    await _run(client, tmp_path, "--alarm-chance", "0")

    boots = [
        m for m in await _messages(session_maker, SENSOR_ID) if m.msg_type == "BOOT"
    ]
    assert [m.decoded["boot_id"] for m in boots] == [1, 2]
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved[SENSOR_ID]["boot_id"] == 2


async def test_stary_plik_stanu_bez_boot_id_dziala(tmp_path):
    (tmp_path / "state.json").write_text(
        json.dumps(
            {SENSOR_ID: {"id": SENSOR_ID, "counter": 7, "battery": 90, "silent": False}}
        )
    )
    [sensor] = load_state(tmp_path / "state.json", [SENSOR_ID])
    assert (sensor.counter, sensor.boot_id) == (7, 0)


async def test_skasowany_plik_stanu_symulator_sam_przeskakuje_boot_id(
    client, session_maker, two_sensors, tmp_path, caplog
):
    """Plik stanu starszy niż baza: BOOT z boot_id 1 to powtórka, symulator przeskakuje o 2^14."""
    await _run(client, tmp_path, "--alarm-chance", "0")
    (tmp_path / "state.json").unlink()  # symulator zaczyna boot_id od nowa, baza pamięta 1
    with caplog.at_level(logging.WARNING, logger="simulator"):
        await _run(client, tmp_path, "--alarm-chance", "0")
    assert "próbuję 16385" in caplog.text

    msgs = await _messages(session_maker, SENSOR_ID)
    assert [(m.msg_type, m.decoded["header"]["boot_id"]) for m in msgs] == [
        ("BOOT", 1), ("HEARTBEAT", 1), ("BOOT", 16385), ("HEARTBEAT", 16385),
    ]


async def test_dwa_symulatory_naraz_ten_w_tle_sam_wraca(
    client, session_maker, two_sensors, tmp_path
):
    """Scenariusz uruchomiony obok symulatora w tle restartuje czujnik nowszym boot_id.
    Symulator w tle dostaje wtedy duplicate, wysyła nowy BOOT i ponawia heartbeat."""
    bg = Simulator(client, [VirtualSensor(id=SENSOR_ID)])
    other = Simulator(client, [VirtualSensor(id=SENSOR_ID, boot_id=5)])
    await bg.boot(bg.sensors[0])  # boot_id 1
    await other.boot(other.sensors[0])  # boot_id 6: nowsza sesja w bazie

    results = await bg.heartbeat(bg.sensors[0])
    assert [r["status"] for r in results] == ["stored"]
    assert bg.sensors[0].boot_id > 6
    msgs = await _messages(session_maker, SENSOR_ID)
    assert msgs[-1].msg_type == "HEARTBEAT"
    assert msgs[-1].decoded["header"]["boot_id"] == bg.sensors[0].boot_id


KEY = "00112233445566778899aabbccddeeff"


async def test_szyfrowane_ramki_przy_kluczu(
    client, session_maker, two_sensors, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "frame_aes_key", KEY)
    await _run(client, tmp_path, "--scenario", "theft", "--target", SECOND, "--aes-key", KEY)
    assert [m.msg_type for m in await _messages(session_maker, SECOND)] == [
        "BOOT", "ALARM", "ALARM", "ALARM", "HEARTBEAT",
    ]
    async with session_maker() as s:
        assert (await s.scalar(select(Alarm))).repeats == 3


async def test_jawne_ramki_przy_kluczu_w_backendzie_podpowiada(
    client, session_maker, two_sensors, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "frame_aes_key", KEY)
    with caplog.at_level(logging.ERROR, logger="simulator"):
        await _run(client, tmp_path, "--alarm-chance", "0", "--aes-key", "")
    assert "FRAME_AES_KEY" in caplog.text and "--aes-key" in caplog.text
    assert await _messages(session_maker, SENSOR_ID) == []


def test_zly_klucz_aes_to_blad_opcji():
    with pytest.raises(SystemExit):
        parse_args(["--aes-key", "abcd"])
    assert parse_args(["--aes-key", KEY]).aes_key == bytes.fromhex(KEY)
    assert parse_args(["--aes-key", ""]).aes_key is None


async def test_fresh_zaczyna_od_pelnych_baterii(tmp_path):
    (tmp_path / "state.json").write_text(
        json.dumps({SENSOR_ID: {"id": SENSOR_ID, "counter": 9, "battery": 0, "boot_id": 4}})
    )
    [kept] = load_state(tmp_path / "state.json", [SENSOR_ID])
    [fresh] = load_state(tmp_path / "state.json", [SENSOR_ID], fresh=True)
    assert (kept.battery, kept.boot_id) == (0, 4)
    assert (fresh.battery, fresh.boot_id, fresh.counter) == (95, 0, 0)
