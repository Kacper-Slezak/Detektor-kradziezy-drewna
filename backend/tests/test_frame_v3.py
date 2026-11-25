"""Ramka wersji 3: boot_id w nagłówku każdej ramki.

Ochrona przed powtórką parą (boot_id, licznik).
"""

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import func, select

from app.config import settings
from app.models import Alarm, Message, Sensor
from app.protocol.decoder import FrameError, decode, frame_length
from app.protocol.encoder import encode_alarm, encode_boot, encode_heartbeat
from app.services.ingest import is_replay
from tests.conftest import SENSOR_ID
from tests.utils import auth

V3 = 3


def boot(counter, boot_id) -> str:
    return encode_boot(counter, battery_pct=88, boot_id=boot_id, version=V3).hex()


def heartbeat(counter, boot_id) -> str:
    return encode_heartbeat(counter, battery_pct=88, boot_id=boot_id, version=V3).hex()


def alarm(counter, boot_id) -> str:
    return encode_alarm(
        counter,
        sources=["microphone", "vibration"],
        confidence=90,
        duration_s=60,
        energy=200,
        battery_pct=88,
        boot_id=boot_id,
        version=V3,
    ).hex()


async def post(client, payload_hex):
    return await client.post(
        "/api/v1/ingest", json={"device": SENSOR_ID, "payload_hex": payload_hex}
    )


async def status(client, payload_hex) -> str | int:
    r = await post(client, payload_hex)
    return r.json()["status"] if r.status_code < 300 else r.status_code


async def state(session_maker) -> tuple[int | None, int | None]:
    async with session_maker() as s:
        sensor = await s.get(Sensor, SENSOR_ID)
        return sensor.last_boot_id, sensor.last_counter


async def count(session_maker, model) -> int:
    async with session_maker() as s:
        return await s.scalar(select(func.count()).select_from(model))


# --- format ---


def test_przyklady_z_dokumentacji():
    assert boot(1, 42) == "33002a0001010158"
    assert heartbeat(2, 42) == "32002a0002580000"
    assert alarm(3, 42) == "31002a000301035a003cc858"


@pytest.mark.parametrize(
    "payload_hex, length", [(boot(1, 7), 8), (heartbeat(2, 7), 8), (alarm(3, 7), 12)]
)
def test_dlugosci_i_naglowek(payload_hex, length):
    payload = bytes.fromhex(payload_hex)
    assert len(payload) == length == frame_length(payload[0])
    frame = decode(payload)
    assert (frame.header.version, frame.header.boot_id) == (3, 7)


def test_boot_v3_boot_id_z_naglowka():
    frame = decode(bytes.fromhex(boot(1, 65535)))
    assert frame.boot_id == frame.header.boot_id == 65535
    assert (frame.firmware_version, frame.reset_reason, frame.battery_pct) == (1, 1, 88)


@pytest.mark.parametrize("payload_hex", ["33002a00010101", "31002a000301035a003cc85800"])
def test_zla_dlugosc(payload_hex):
    with pytest.raises(FrameError, match="wersji 3"):
        decode(bytes.fromhex(payload_hex))


def test_koder_v3_wymaga_boot_id():
    with pytest.raises(ValueError, match="boot_id"):
        encode_heartbeat(1, battery_pct=50, version=V3)


# --- is_replay ---


@pytest.mark.parametrize(
    "last, new, replay",
    [
        ((None, None), (1, 1), False),  # pierwszy kontakt
        ((5, 10), (5, 11), False),  # ta sama sesja, licznik rośnie
        ((5, 10), (5, 10), True),  # duplikat
        ((5, 10), (5, 9), True),  # starsza ramka z tej sesji
        ((5, 10), (6, 1), False),  # nowa sesja, licznik od nowa
        ((5, 10), (6, 500), False),  # nowa sesja, BOOT zginął
        ((5, 10), (4, 50), True),  # ramka z poprzedniej sesji
        ((65535, 3), (0, 1), False),  # przekręcenie boot_id
        ((5, 65535), (5, 0), False),  # przekręcenie licznika
        ((5, 10), (5 + 40000, 1), True),  # skok o > połowę zakresu = stary numer
    ],
)
def test_is_replay(last, new, replay):
    assert is_replay(*last, *new) is replay


# --- /ingest ---


async def test_sesja_od_boot(client, session_maker):
    assert await status(client, boot(1, 1)) == "stored"
    assert await status(client, heartbeat(2, 1)) == "stored"
    r = await post(client, alarm(3, 1))
    assert r.json()["alarm_created"] is True
    assert await state(session_maker) == (1, 3)


async def test_duplikat_w_sesji(client, session_maker):
    await post(client, boot(1, 1))
    await post(client, heartbeat(2, 1))
    assert await status(client, heartbeat(2, 1)) == "duplicate"
    assert await count(session_maker, Message) == 2


async def test_powtorka_starego_alarmu_po_restarcie(client, session_maker):
    """Luka wersji 2: po prawdziwym restarcie stary ALARM przechodził. W wersji 3 nie."""
    await post(client, boot(1, 1))
    stary = alarm(50, 1)
    assert await status(client, stary) == "stored"
    assert await status(client, boot(1, 2)) == "stored"  # prawdziwy restart
    assert await status(client, stary) == "duplicate"
    assert await state(session_maker) == (2, 1)


async def test_powtorka_boot_nie_resetuje_licznika(client, session_maker):
    await post(client, boot(1, 3))
    await post(client, alarm(7, 3))
    assert await status(client, boot(1, 3)) == "duplicate"
    assert await status(client, boot(1, 2)) == "duplicate"
    assert await state(session_maker) == (3, 7)


async def test_nowa_sesja_bez_boot(client, session_maker):
    """BOOT zginął w radiu: pierwsza ramka nowej sesji i tak zostaje przyjęta."""
    await post(client, boot(1, 1))
    await post(client, heartbeat(2, 1))
    assert await status(client, alarm(3, 2)) == "stored"
    assert await state(session_maker) == (2, 3)


async def test_przejscie_z_v2_na_v3(client, session_maker):
    await post(client, encode_boot(1, battery_pct=88, boot_id=10).hex())  # wersja 2
    await post(client, encode_heartbeat(2, battery_pct=88).hex())  # wersja 1
    assert await state(session_maker) == (10, 2)
    assert await status(client, boot(1, 11)) == "stored"
    assert await status(client, boot(1, 10)) == "duplicate"


async def test_boot_v1_po_v3_odrzucony(client):
    await post(client, boot(1, 1))
    assert await status(client, encode_boot(1, battery_pct=88).hex()) == 422


async def test_legacy_wylaczone(client, session_maker, monkeypatch):
    monkeypatch.setattr(settings, "legacy_frames", False)
    for payload in (
        encode_boot(1, battery_pct=88).hex(),
        encode_boot(1, battery_pct=88, boot_id=5).hex(),
        encode_heartbeat(2, battery_pct=88).hex(),
    ):
        r = await post(client, payload)
        assert r.status_code == 422
        assert "LEGACY_FRAMES" in r.json()["detail"]
    assert await status(client, boot(1, 1)) == "stored"
    assert await count(session_maker, Message) == 1


async def test_reset_boot_po_wymianie_plytki(client, session_maker, make_user):
    await make_user("admin", role="admin")
    await post(client, boot(1, 500))
    assert await status(client, boot(1, 1)) == "duplicate"  # nowa płytka liczy od 1
    r = await client.post(
        f"/api/v1/sensors/{SENSOR_ID}/reset-boot", headers=await auth(client, "admin")
    )
    assert r.status_code == 204
    assert await status(client, boot(1, 1)) == "stored"
    assert await state(session_maker) == (1, 1)


async def test_zaszyfrowany_alarm_v3(client, session_maker, monkeypatch):
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    monkeypatch.setattr(settings, "frame_aes_key", key.hex())

    def encrypt(frame_hex):
        e = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        return (e.update(bytes.fromhex(frame_hex).ljust(16, b"\x00")) + e.finalize()).hex()

    assert await status(client, encrypt(boot(1, 1))) == "stored"
    r = await post(client, encrypt(alarm(2, 1)))
    assert r.status_code == 201 and r.json()["alarm_created"] is True
    async with session_maker() as s:
        saved = await s.scalar(select(Message.payload_hex).where(Message.counter == 2))
    assert saved == alarm(2, 1)  # w bazie jawna ramka 12 B
    assert await count(session_maker, Alarm) == 1
