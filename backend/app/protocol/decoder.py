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

