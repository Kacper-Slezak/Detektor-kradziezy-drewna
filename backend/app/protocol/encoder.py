"""Koder ramek: odwrotność decoder.py. Pakuje ramki tak samo jak firmware.

Używają go seed danych demo (historia w bazie) i symulator czujników (tools/simulator.py).
Firmware pisze to samo w MicroPythonie: ten plik jest wzorem, a testy pilnują,
że to, co tu spakujemy, dekoder odczyta bez zmian.

Wersja 3 (`version=3`, wymaga `boot_id`): boot_id w nagłówku każdej ramki.
Bez `version` funkcje pakują jak dotąd: wersja 1, a BOOT z `boot_id` jako wersja 2.
"""

from app.protocol.decoder import (
    BODY,
    BOOT_V2_BODY,
    HEADER,
    HEADER_V3,
    SESSION_VERSION,
    SOURCE_BITS,
    MsgType,
)

VERSION = 1
VERSION_BOOT_ID = 2  # BOOT z boot_id w treści
VERSION_SESSION = SESSION_VERSION  # 3: boot_id w nagłówku każdej ramki
_SOURCE_BIT = {name: bit for bit, name in SOURCE_BITS.items()}
_MOD = 1 << 16


def _header(
    msg_type: MsgType, counter: int, version: int = VERSION, boot_id: int | None = None
) -> bytes:
    first = (version << 4) | msg_type
    if version >= VERSION_SESSION:
        if boot_id is None:
            raise ValueError(f"ramka wersji {version} wymaga boot_id")
        return HEADER_V3.pack(first, boot_id % _MOD, counter % _MOD)
    return HEADER.pack(first, counter % _MOD)


def encode_alarm(
    counter: int,
    *,
    event_type: int = 1,
    sources: list[str] = ("microphone",),
    confidence: int,
    duration_s: int,
    energy: int,
    battery_pct: int,
    version: int = VERSION,
    boot_id: int | None = None,
) -> bytes:
    source_bits = 0
    for name in sources:
        source_bits |= 1 << _SOURCE_BIT[name]
    body = BODY[MsgType.ALARM].pack(
        event_type, source_bits, confidence, duration_s, energy, battery_pct
    )
    return _header(MsgType.ALARM, counter, version, boot_id) + body


def encode_heartbeat(
    counter: int,
    *,
    battery_pct: int,
    rejected_events: int = 0,
    locked: bool = False,
    low_battery: bool = False,
    sensor_error: bool = False,
    version: int = VERSION,
    boot_id: int | None = None,
) -> bytes:
    flags = (locked << 0) | (low_battery << 1) | (sensor_error << 2)
    body = BODY[MsgType.HEARTBEAT].pack(battery_pct, rejected_events, flags)
    return _header(MsgType.HEARTBEAT, counter, version, boot_id) + body


def encode_boot(
    counter: int,
    *,
    firmware_version: int = 1,
    reset_reason: int = 1,
    battery_pct: int,
    boot_id: int | None = None,
    version: int | None = None,
) -> bytes:
    """Bez `version`: bez `boot_id` ramka wersji 1 (6 B), z nim wersji 2 (8 B).

    `version=3`: boot_id w nagłówku, treść jak w wersji 1 (razem 8 B).
    """
    if version is None:
        version = VERSION if boot_id is None else VERSION_BOOT_ID
    if version == VERSION_BOOT_ID:
        if boot_id is None:
            raise ValueError("BOOT wersji 2 wymaga boot_id")
        body = BOOT_V2_BODY.pack(firmware_version, reset_reason, battery_pct, boot_id % _MOD)
        return _header(MsgType.BOOT, counter, VERSION_BOOT_ID) + body
    body = BODY[MsgType.BOOT].pack(firmware_version, reset_reason, battery_pct)
    return _header(MsgType.BOOT, counter, version, boot_id) + body
