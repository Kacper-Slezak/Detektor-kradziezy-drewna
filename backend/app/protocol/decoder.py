"""Dekoder ramek urządzenie -> serwer, wg docs/protocol.md.
"""

import struct
from dataclasses import asdict, dataclass
from enum import IntEnum

SUPPORTED_VERSIONS = {1}
HEADER = struct.Struct(">BH")  # wersja|typ, licznik


class FrameError(ValueError):
    """Ramka nie do odczytania (za krótka, zła wersja, zły typ...)."""


class MsgType(IntEnum):
    ALARM = 1
    HEARTBEAT = 2
    BOOT = 3


# bit -> nazwa źródła (pole "źródło" w ALARM)
SOURCE_BITS = {0: "microphone", 1: "vibration"}


@dataclass(frozen=True)
class Header:
    version: int
    msg_type: MsgType
    counter: int


@dataclass(frozen=True)
class AlarmFrame:
    header: Header
    event_type: int  # listę rodzajów ustala Kiryl
    sources: list[str]
    confidence: int  # 0-100
    duration_s: int
    energy: int  # 0-255
    battery_pct: int


@dataclass(frozen=True)
class HeartbeatFrame:
    header: Header
    battery_pct: int
    rejected_events: int
    locked: bool
    low_battery: bool
    sensor_error: bool


@dataclass(frozen=True)
class BootFrame:
    header: Header
    firmware_version: int
    reset_reason: int  # 1 włączenie, 2 watchdog, 3 za niskie napięcie
    battery_pct: int


Frame = AlarmFrame | HeartbeatFrame | BootFrame

# typ -> układ bajtów PO nagłówku
BODY = {
    MsgType.ALARM: struct.Struct(">BBBHBB"),  # rodzaj, źródło, pewność, czas, energia, bateria
    MsgType.HEARTBEAT: struct.Struct(">BBB"),  # bateria, odrzucone, flagi
    MsgType.BOOT: struct.Struct(">BBB"),  # firmware, przyczyna, bateria
}


def _percent(value: int, field: str) -> int:
    if value > 100:
        raise FrameError(f"{field} = {value}, a powinno być 0-100")
    return value


def decode(payload: bytes) -> Frame:
    if len(payload) < HEADER.size:
        raise FrameError(f"za krótka ramka: {len(payload)} B, nagłówek ma {HEADER.size} B")

    first, counter = HEADER.unpack_from(payload)
    version, type_code = first >> 4, first & 0x0F

    if version not in SUPPORTED_VERSIONS:
        raise FrameError(f"nieobsługiwana wersja ramki: {version}")
    try:
        msg_type = MsgType(type_code)
    except ValueError:
        raise FrameError(f"nieznany typ wiadomości: {type_code}") from None

    body = BODY[msg_type]
    expected = HEADER.size + body.size
    if len(payload) != expected:
        raise FrameError(f"{msg_type.name}: oczekiwano {expected} B, jest {len(payload)} B")

    header = Header(version, msg_type, counter)
    fields = body.unpack_from(payload, HEADER.size)

    if msg_type is MsgType.ALARM:
        event_type, source_bits, confidence, duration_s, energy, battery = fields
        sources = [name for bit, name in SOURCE_BITS.items() if source_bits & (1 << bit)]
        return AlarmFrame(
            header, event_type, sources, _percent(confidence, "pewność"),
            duration_s, energy, _percent(battery, "bateria"),
        )

    if msg_type is MsgType.HEARTBEAT:
        battery, rejected, flags = fields
        return HeartbeatFrame(
            header, _percent(battery, "bateria"), rejected,
            locked=bool(flags & 0b001),
            low_battery=bool(flags & 0b010),
            sensor_error=bool(flags & 0b100),
        )

    firmware, reason, battery = fields
    return BootFrame(header, firmware, reason, _percent(battery, "bateria"))


def decode_hex(payload_hex: str) -> Frame:
    try:
        payload = bytes.fromhex(payload_hex)
    except ValueError:
        raise FrameError("payload_hex to nie jest poprawny hex") from None
    return decode(payload)


def to_dict(frame: Frame) -> dict:
    """Do zapisu w bazie (kolumna JSON)."""
    data = asdict(frame)
    data["header"]["msg_type"] = frame.header.msg_type.name
    return data
