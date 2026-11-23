import pytest

from app.protocol.decoder import (
    AlarmFrame,
    BootFrame,
    FrameError,
    HeartbeatFrame,
    MsgType,
    decode_hex,
    to_dict,
)


def test_alarm_z_protokolu():
    # przykład z docs/protocol.md
    f = decode_hex("11002A0101570028B440")
    assert isinstance(f, AlarmFrame)
    assert f.header.version == 1
    assert f.header.msg_type is MsgType.ALARM
    assert f.header.counter == 42
    assert f.event_type == 1
    assert f.sources == ["microphone"]
    assert f.confidence == 87
    assert f.duration_s == 40
    assert f.energy == 180
    assert f.battery_pct == 64


def test_alarm_oba_zrodla():
    f = decode_hex("11002B0103570028B440")
    assert f.sources == ["microphone", "vibration"]


def test_heartbeat():
    # bateria 64%, 12 odrzuconych, flagi: zablokowany + niska bateria
    f = decode_hex("120007" "40" "0C" "03")
    assert isinstance(f, HeartbeatFrame)
    assert f.header.counter == 7
    assert (f.battery_pct, f.rejected_events) == (64, 12)
    assert f.locked and f.low_battery and not f.sensor_error


def test_boot():
    f = decode_hex("130000" "05" "02" "63")
    assert isinstance(f, BootFrame)
    assert (f.firmware_version, f.reset_reason, f.battery_pct) == (5, 2, 99)


def test_to_dict_do_bazy():
    d = to_dict(decode_hex("11002A0101570028B440"))
    assert d["header"]["msg_type"] == "ALARM"
    assert d["confidence"] == 87


@pytest.mark.parametrize(
    "payload, fragment",
    [
        ("11", "za krótka"),
        ("31002A0101570028B440", "wersja"),  # wersja 3: nieobsługiwana
        ("14002A", "typ"),  # typ 4 nie istnieje
        ("11002A01015700", "oczekiwano 10"),  # ALARM ucięty
        ("11002A0101570028B44000", "oczekiwano 10"),  # bajt za dużo
        ("11002A01016500 28B440".replace(" ", ""), "pewność"),  # pewność 101
        ("zz", "hex"),
    ],
)
def test_bledne_ramki(payload, fragment):
    with pytest.raises(FrameError, match=fragment):
        decode_hex(payload)


# --- wersja 2: BOOT z boot_id ---


def test_boot_wersji_2_ma_boot_id():
    f = decode_hex("23" "0001" "01" "01" "58" "002A")
    assert isinstance(f, BootFrame)
    assert f.header.version == 2 and f.header.counter == 1
    assert (f.firmware_version, f.reset_reason, f.battery_pct, f.boot_id) == (1, 1, 88, 42)
    assert to_dict(f)["boot_id"] == 42


def test_boot_wersji_1_nie_ma_boot_id():
    assert decode_hex("130001010158").boot_id is None


def test_alarm_i_heartbeat_wersji_2_maja_ten_sam_uklad():
    alarm = decode_hex("21002A0101570028B440")
    assert isinstance(alarm, AlarmFrame) and alarm.header.version == 2
    assert alarm.sources == ["microphone"] and alarm.confidence == 87
    assert isinstance(decode_hex("22000740" "0C" "03"), HeartbeatFrame)


@pytest.mark.parametrize(
    "payload, fragment",
    [
        ("230001010158", "oczekiwano 8"),  # wersja 2 bez boot_id
        ("130001010158002A", "oczekiwano 6"),  # wersja 1 nie ma miejsca na boot_id
    ],
)
def test_boot_zla_dlugosc_dla_wersji(payload, fragment):
    with pytest.raises(FrameError, match=fragment):
        decode_hex(payload)


@pytest.mark.parametrize(
    "first_byte, length",
    [(0x11, 10), (0x12, 6), (0x13, 6), (0x21, 10), (0x22, 6), (0x23, 8)],
)
def test_frame_length(first_byte, length):
    from app.protocol.decoder import frame_length

    assert frame_length(first_byte) == length


@pytest.mark.parametrize("first_byte, fragment", [(0x33, "wersja"), (0x14, "typ")])
def test_frame_length_bledny_pierwszy_bajt(first_byte, fragment):
    from app.protocol.decoder import frame_length

    with pytest.raises(FrameError, match=fragment):
        frame_length(first_byte)
