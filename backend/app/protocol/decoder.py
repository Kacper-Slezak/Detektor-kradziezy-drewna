"""Dekoder ramek urządzenie -> serwer, wg docs/protocol.md.
"""

import struct
from dataclasses import asdict, dataclass
from enum import IntEnum

# 1 = pierwotna, 2 = BOOT niesie boot_id (przejściowo, docs/backend/boot-id.md),
# 3 = boot_id w nagłówku KAŻDEJ ramki: para (boot_id, licznik) chroni przed powtórkami
SUPPORTED_VERSIONS = {1, 2, 3}
SESSION_VERSION = 3  # od tej wersji boot_id jest w nagłówku
HEADER = struct.Struct(">BH")  # wersje 1 i 2: wersja|typ, licznik
HEADER_V3 = struct.Struct(">BHH")  # wersja 3: wersja|typ, boot_id, licznik


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
    # wersja 3: numer uruchomienia płytki (sesji) z nagłówka; w wersjach 1 i 2 brak
    boot_id: int | None = None


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
    # numer uruchomienia, rośnie przy każdym starcie (pamięć nieulotna płytki):
    # wersja 2 z treści BOOT, wersja 3 z nagłówka; w wersji 1 brak
    boot_id: int | None = None


Frame = AlarmFrame | HeartbeatFrame | BootFrame

# typ -> układ bajtów PO nagłówku
BODY = {
    MsgType.ALARM: struct.Struct(">BBBHBB"),  # rodzaj, źródło, pewność, czas, energia, bateria
    MsgType.HEARTBEAT: struct.Struct(">BBB"),  # bateria, odrzucone, flagi
    MsgType.BOOT: struct.Struct(">BBB"),  # firmware, przyczyna, bateria
}


# BOOT w wersji 2: to samo co w 1 plus boot_id (2 B). Ramka jawna ma wtedy 8 B zamiast 6 B.
BOOT_V2_BODY = struct.Struct(">BBBH")  # firmware, przyczyna, bateria, boot_id


def header_struct(version: int) -> struct.Struct:
    """Układ nagłówka: wersja 3 ma boot_id (5 B), wersje 1 i 2 nie (3 B)."""
    return HEADER_V3 if version >= SESSION_VERSION else HEADER


def body_struct(version: int, msg_type: MsgType) -> struct.Struct:
    """Układ bajtów po nagłówku. Różni się tylko BOOT wersji 2: ma boot_id w treści.

    W wersji 3 boot_id jest w nagłówku, więc treść BOOT jest taka jak w wersji 1.
    """
    if msg_type is MsgType.BOOT and version == 2:
        return BOOT_V2_BODY
    return BODY[msg_type]


def frame_length(first_byte: int) -> int:
    """Długość jawnej ramki w bajtach według pierwszego bajtu (wersja i typ).

    Dla warstwy szyfrującej, która obcina dopełnienie zerami po odszyfrowaniu.
    """
    version, type_code = first_byte >> 4, first_byte & 0x0F
    if version not in SUPPORTED_VERSIONS:
        raise FrameError(f"nieobsługiwana wersja ramki: {version}")
    try:
        msg_type = MsgType(type_code)
    except ValueError:
        raise FrameError(f"nieznany typ wiadomości: {type_code}") from None
    return header_struct(version).size + body_struct(version, msg_type).size


def _percent(value: int, field: str) -> int:
    if value > 100:
        raise FrameError(f"{field} = {value}, a powinno być 0-100")
    return value


def decode(payload: bytes) -> Frame:
    if len(payload) < HEADER.size:
        raise FrameError(f"za krótka ramka: {len(payload)} B, nagłówek ma {HEADER.size} B")

    version = payload[0] >> 4
    type_code = payload[0] & 0x0F

    if version not in SUPPORTED_VERSIONS:
        raise FrameError(f"nieobsługiwana wersja ramki: {version}")
    try:
        msg_type = MsgType(type_code)
    except ValueError:
        raise FrameError(f"nieznany typ wiadomości: {type_code}") from None

    head = header_struct(version)
    body = body_struct(version, msg_type)
    expected = head.size + body.size
    if len(payload) != expected:
        raise FrameError(
            f"{msg_type.name} wersji {version}: oczekiwano {expected} B, jest {len(payload)} B"
        )

    if version >= SESSION_VERSION:
        _, boot_id, counter = head.unpack_from(payload)
        header = Header(version, msg_type, counter, boot_id)
    else:
        _, counter = head.unpack_from(payload)
        header = Header(version, msg_type, counter)
    fields = body.unpack_from(payload, head.size)

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

    firmware, reason, battery, *rest = fields
    boot_id = rest[0] if rest else header.boot_id  # wersja 2: z treści, wersja 3: z nagłówka
    return BootFrame(header, firmware, reason, _percent(battery, "bateria"), boot_id=boot_id)


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



# Szyfrowanie ramek (AES-128)
# Urządzenie dopełnia jawną ramkę zerami do 16 B (jeden blok AES) i szyfruje ją AES-128-ECB.
# Przy ustawionym FRAME_AES_KEY backend przyjmuje TYLKO zaszyfrowane ramki (16 B):
# jawna ramka -> 422, inaczej fałszywy alarm dałoby się wysłać bez znajomości klucza.

AES_BLOCK = 16


def parse_aes_key(key_hex: str) -> bytes | None:
    """FRAME_AES_KEY z .env (32 znaki hex) -> 16 B; pusty -> None (szyfrowanie wyłączone)."""
    if not key_hex:
        return None
    try:
        key = bytes.fromhex(key_hex)
    except ValueError:
        raise ValueError("FRAME_AES_KEY to nie jest poprawny hex") from None
    if len(key) != AES_BLOCK:
        raise ValueError(
            f"FRAME_AES_KEY ma {len(key)} B, a powinien mieć {AES_BLOCK} B (32 znaki hex)"
        )
    return key


def decrypt_payload_hex(payload_hex: str, key: bytes | None) -> str:
    """Zaszyfrowana ramka (16 B) -> hex jawnej ramki.

    Bez klucza (szyfrowanie wyłączone) zwraca payload bez zmian.
    Z kluczem każda ramka musi być zaszyfrowana: inna długość niż 16 B -> FrameError (422).
    """
    if key is None:
        return payload_hex
    try:
        data = bytes.fromhex(payload_hex)
    except ValueError:
        raise FrameError("payload_hex to nie jest poprawny hex") from None
    if len(data) != AES_BLOCK:
        raise FrameError(
            f"oczekiwano zaszyfrowanej ramki ({AES_BLOCK} B), jest {len(data)} B; "
            "jawne ramki są odrzucane, gdy ustawiony jest FRAME_AES_KEY"
        )

    # import tutaj, żeby dekoder (i symulator) działał bez pakietu cryptography
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    block = decryptor.update(data) + decryptor.finalize()

    # Długość jawnej ramki z pierwszego bajtu (wersja i typ), np. BOOT v1 = 6 B, BOOT v2 = 8 B
    # (z boot_id), ALARM = 10 B. Nie z BODY[typ].size: obcięłoby boot_id z BOOT-a wersji 2.
    # Zły klucz albo losowy pakiet daje losowe bajty. Sam pierwszy bajt (wersja, typ) to za mało:
    # losowy pakiet bez klucza przechodził wtedy jako ramka w ok. 0,7% prób. Dlatego dopełnienie
    # musi być zerami: jedyny test integralności bez podpisu (MIC), szansa 2^-32 .. 2^-80.
    try:
        length = frame_length(block[0])
    except FrameError:
        length = None
    if length is None or any(block[length:]):
        raise FrameError(
            "nie da się odszyfrować ramki (zły klucz albo uszkodzony pakiet)"
        )
    return block[:length].hex()
