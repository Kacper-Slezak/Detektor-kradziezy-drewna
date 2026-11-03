"""Koder ramek: odwrotność decoder.py. Pakuje ramki tak samo jak firmware.

Używają go seed danych demo (historia w bazie) i symulator czujników (tools/simulator.py).
Firmware pisze to samo w MicroPythonie: ten plik jest wzorem, a testy pilnują,
że to, co tu spakujemy, dekoder odczyta bez zmian.
"""

from app.protocol.decoder import BODY, HEADER, SOURCE_BITS, MsgType

VERSION = 1
_SOURCE_BIT = {name: bit for bit, name in SOURCE_BITS.items()}


def _header(msg_type: MsgType, counter: int) -> bytes:
    return HEADER.pack((VERSION << 4) | msg_type, counter % (1 << 16))


def encode_alarm(
    counter: int,
    *,
    event_type: int = 1,
    sources: list[str] = ("microphone",),
    confidence: int,
    duration_s: int,
    energy: int,
    battery_pct: int,
) -> bytes:
    source_bits = 0
    for name in sources:
        source_bits |= 1 << _SOURCE_BIT[name]
    body = BODY[MsgType.ALARM].pack(
        event_type, source_bits, confidence, duration_s, energy, battery_pct
    )
    return _header(MsgType.ALARM, counter) + body


def encode_heartbeat(
    counter: int,
    *,
    battery_pct: int,
    rejected_events: int = 0,
    locked: bool = False,
    low_battery: bool = False,
    sensor_error: bool = False,
) -> bytes:
    flags = (locked << 0) | (low_battery << 1) | (sensor_error << 2)
    body = BODY[MsgType.HEARTBEAT].pack(battery_pct, rejected_events, flags)
    return _header(MsgType.HEARTBEAT, counter) + body


def encode_boot(
    counter: int, *, firmware_version: int = 1, reset_reason: int = 1, battery_pct: int
) -> bytes:
    body = BODY[MsgType.BOOT].pack(firmware_version, reset_reason, battery_pct)
    return _header(MsgType.BOOT, counter) + body
