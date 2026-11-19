"""Szyfrowane ramki (AES-128-ECB, 1 blok) przez POST /api/v1/ingest."""

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.protocol.decoder import FrameError, decrypt_payload_hex, parse_aes_key
from app.routers import ingest as ingest_router
from tests.conftest import SENSOR_ID

KEY = bytes.fromhex("00112233445566778899aabbccddeeff")
HEARTBEAT = (
    "120000400c00"
)
ALARM = "11002a0101570028b440"


def encrypt(frame_hex: str, key: bytes = KEY) -> str:
    block = bytes.fromhex(frame_hex).ljust(16, b"\x00")
    e = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return (e.update(block) + e.finalize()).hex()


def test_odszyfrowanie_heartbeat_i_alarm():
    assert decrypt_payload_hex(encrypt(HEARTBEAT), KEY) == HEARTBEAT
    assert decrypt_payload_hex(encrypt(ALARM), KEY) == ALARM


def test_wektor_lopy():
    assert encrypt("130001010158") == "4e8b49d27d5b10a107cfd1092f329126"


def test_jawne_ramki_bez_zmian():
    assert decrypt_payload_hex(ALARM, KEY) == ALARM
    assert decrypt_payload_hex(encrypt(ALARM), None) == encrypt(ALARM)


def test_zly_klucz():
    with pytest.raises(FrameError):
        for i in range(20):
            decrypt_payload_hex(encrypt(f"1200{i:02x}400c00"), bytes(16))


def test_parse_aes_key():
    assert parse_aes_key("") is None
    assert parse_aes_key(KEY.hex()) == KEY
    with pytest.raises(ValueError):
        parse_aes_key("abcd")


async def test_ingest_szyfrowana_ramka(client, monkeypatch):
    monkeypatch.setattr(ingest_router, "FRAME_AES_KEY", KEY)
    r = await client.post(
        "/api/v1/ingest", json={"device": SENSOR_ID, "payload_hex": encrypt(ALARM)}
    )
    assert r.status_code == 201
    assert r.json()["alarm_created"] is True


async def test_ingest_zly_klucz_422(client, monkeypatch):
    monkeypatch.setattr(ingest_router, "FRAME_AES_KEY", KEY)
    r = await client.post(
        "/api/v1/ingest",
        json={"device": SENSOR_ID, "payload_hex": encrypt(ALARM, bytes(range(16)))},
    )
    assert r.status_code == 422
