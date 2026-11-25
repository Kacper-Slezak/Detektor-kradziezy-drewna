"""Szyfrowane ramki (AES-128-ECB, 1 blok) przez POST /api/v1/ingest."""

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import settings
from app.models import Sensor
from app.protocol.decoder import FrameError, decrypt_payload_hex, parse_aes_key
from app.protocol.encoder import encode_boot
from tests.conftest import SENSOR_ID

KEY = bytes.fromhex("00112233445566778899aabbccddeeff")
HEARTBEAT = "120000400c00"  # kończy się 00 00: dopełnienia nie wolno obcinać "po zerach"
ALARM = "11002a0101570028b440"
BOOT_V2 = encode_boot(1, battery_pct=88, boot_id=42).hex()  # 8 B, boot_id na końcu


def encrypt(frame_hex: str, key: bytes = KEY) -> str:
    block = bytes.fromhex(frame_hex).ljust(16, b"\x00")
    e = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return (e.update(block) + e.finalize()).hex()


@pytest.fixture
def aes_on(monkeypatch):
    monkeypatch.setattr(settings, "frame_aes_key", KEY.hex())


async def post(client, payload_hex):
    return await client.post(
        "/api/v1/ingest", json={"device": SENSOR_ID, "payload_hex": payload_hex}
    )


# --- decrypt_payload_hex ---


def test_odszyfrowanie_heartbeat_i_alarm():
    assert decrypt_payload_hex(encrypt(HEARTBEAT), KEY) == HEARTBEAT
    assert decrypt_payload_hex(encrypt(ALARM), KEY) == ALARM


def test_odszyfrowanie_boot_v2_zachowuje_boot_id():
    # BOOT wersji 2 ma 8 B: długość z frame_length(), a nie z BODY[BOOT] (6 B)
    assert len(bytes.fromhex(BOOT_V2)) == 8
    assert decrypt_payload_hex(encrypt(BOOT_V2), KEY) == BOOT_V2


def test_wektor_lopy():
    # ten sam wynik co lopy_aes.zaszyfruj() z przykładowym kluczem
    assert encrypt("130001010158") == "4e8b49d27d5b10a107cfd1092f329126"


def test_jawna_ramka_odrzucona_przy_kluczu():
    with pytest.raises(FrameError, match="zaszyfrowanej"):
        decrypt_payload_hex(ALARM, KEY)


def test_bez_klucza_ramka_bez_zmian():
    assert decrypt_payload_hex(ALARM, None) == ALARM


def test_zly_klucz():
    with pytest.raises(FrameError, match="odszyfrować"):
        decrypt_payload_hex(encrypt(ALARM, bytes(range(16))), KEY)


def test_niezerowe_dopelnienie_odrzucone():
    # poprawny pierwszy bajt, ale śmieci w dopełnieniu: tak wygląda losowy pakiet bez klucza
    block = bytes.fromhex(ALARM).ljust(15, b"\x00") + b"\x01"
    e = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    forged = (e.update(block) + e.finalize()).hex()
    with pytest.raises(FrameError, match="odszyfrować"):
        decrypt_payload_hex(forged, KEY)


def test_parse_aes_key():
    assert parse_aes_key("") is None
    assert parse_aes_key(KEY.hex()) == KEY
    with pytest.raises(ValueError):
        parse_aes_key("abcd")
    with pytest.raises(ValueError):
        parse_aes_key("zz" * 16)


# --- POST /api/v1/ingest ---


async def test_ingest_szyfrowana_ramka(client, aes_on):
    r = await post(client, encrypt(ALARM))
    assert r.status_code == 201
    assert r.json()["alarm_created"] is True


async def test_ingest_jawna_ramka_422_przy_kluczu(client, aes_on):
    # bez tego fałszywy alarm dałoby się wysłać bez znajomości klucza
    r = await post(client, ALARM)
    assert r.status_code == 422


async def test_ingest_zly_klucz_422(client, aes_on):
    r = await post(client, encrypt(ALARM, bytes(range(16))))
    assert r.status_code == 422


async def test_ingest_szyfrowany_boot_v2_zapisuje_boot_id(client, session_maker, aes_on):
    r = await post(client, encrypt(BOOT_V2))
    assert r.status_code == 201
    async with session_maker() as s:
        sensor = await s.get(Sensor, SENSOR_ID)
        assert sensor.last_boot_id == 42


async def test_ingest_bez_klucza_jawne_ramki_dzialaja(client):
    r = await post(client, ALARM)
    assert r.status_code == 201
