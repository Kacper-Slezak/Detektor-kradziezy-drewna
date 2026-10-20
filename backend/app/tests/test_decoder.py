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
        ("21002A0101570028B440", "wersja"),  # wersja 2
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
