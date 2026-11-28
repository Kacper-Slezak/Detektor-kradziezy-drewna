"""Koder musi dawać ramki, które dekoder czyta bez zmian (to samo zrobi firmware)."""

from app.protocol.decoder import AlarmFrame, BootFrame, HeartbeatFrame, MsgType, decode
from app.protocol.encoder import encode_alarm, encode_boot, encode_heartbeat


def test_przyklad_z_protokolu():
    frame = encode_alarm(
        42,
        event_type=1,
        sources=["microphone"],
        confidence=87,
        duration_s=40,
        energy=180,
        battery_pct=64,
    )
    assert frame.hex().upper() == "11002A0101570028B440"


def test_alarm_tam_i_z_powrotem():
    frame = decode(
        encode_alarm(
            7,
            sources=["microphone", "vibration"],
            confidence=93,
            duration_s=300,
            energy=255,
            battery_pct=50,
        )
    )
    assert isinstance(frame, AlarmFrame)
    assert frame.header.counter == 7
    assert frame.sources == ["microphone", "vibration"]
    assert (frame.confidence, frame.duration_s, frame.energy, frame.battery_pct) == (
        93,
        300,
        255,
        50,
    )


def test_heartbeat_z_flagami():
    frame = decode(
        encode_heartbeat(65535, battery_pct=15, rejected_events=3, low_battery=True)
    )
    assert isinstance(frame, HeartbeatFrame)
    assert frame.header.msg_type is MsgType.HEARTBEAT
    assert frame.header.counter == 65535
    assert (frame.battery_pct, frame.rejected_events) == (15, 3)
    assert frame.low_battery and not frame.locked and not frame.sensor_error


def test_boot():
    frame = decode(encode_boot(0, firmware_version=3, reset_reason=2, battery_pct=99))
    assert isinstance(frame, BootFrame)
    assert (frame.firmware_version, frame.reset_reason, frame.battery_pct) == (3, 2, 99)


def test_licznik_przekreca_sie():
    assert decode(encode_boot(65536, battery_pct=1)).header.counter == 0


def test_boot_z_boot_id_to_wersja_2():
    payload = encode_boot(5, battery_pct=88, boot_id=42)
    assert len(payload) == 8
    frame = decode(payload)
    assert isinstance(frame, BootFrame)
    assert (frame.header.version, frame.header.counter, frame.boot_id) == (2, 5, 42)


def test_boot_bez_boot_id_zostaje_wersja_1():
    payload = encode_boot(5, battery_pct=88)
    assert len(payload) == 6
    frame = decode(payload)
    assert (frame.header.version, frame.boot_id) == (1, None)


def test_boot_id_przekreca_sie_jak_licznik():
    assert decode(encode_boot(1, battery_pct=1, boot_id=65536)).boot_id == 0


def test_alarm_i_heartbeat_mozna_oznaczyc_wersja_2():
    alarm = encode_alarm(
        1, confidence=80, duration_s=10, energy=100, battery_pct=70, version=2
    )
    assert decode(alarm).header.version == 2
    assert decode(encode_heartbeat(1, battery_pct=70, version=2)).header.version == 2
