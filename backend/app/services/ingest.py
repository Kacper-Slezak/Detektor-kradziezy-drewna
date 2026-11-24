"""Logika odbioru ramki: czujnik -> dekodowanie -> zapis -> alarm."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Alarm, Message, Release, Sensor
from app.protocol.decoder import (
    AlarmFrame,
    HeartbeatFrame,
    MsgType,
    decode_hex,
    to_dict,
)

log = logging.getLogger(__name__)

COUNTER_MOD = 1 << 16  # licznik ma 2 B i się przekręca
# bateria musi wrócić wyraźnie powyżej progu, zanim push o słabej baterii pójdzie znowu
BATTERY_HYSTERESIS_PCT = 5


class UnknownSensorError(Exception):
    pass


@dataclass
class IngestResult:
    status: str  # "stored" albo "duplicate"
    message_id: int | None = None
    alarm_id: int | None = None
    alarm_created: bool = False
    muted: bool = False
    low_battery_push: bool = False  # bateria właśnie stała się słaba (nie trafia do odpowiedzi)


def is_duplicate(last_counter: int | None, counter: int, msg_type: MsgType) -> bool:
    """Ramka z licznikiem nie większym niż ostatni = duplikat albo stara ramka.

    Po BOOT licznik może zacząć od nowa, więc go akceptujemy.
    Uwzględnia przekręcenie 65535 -> 0.
    """
    if last_counter is None or msg_type is MsgType.BOOT:
        return False
    diff = (counter - last_counter) % COUNTER_MOD
    return diff == 0 or diff > COUNTER_MOD // 2


def _track_battery(sensor: Sensor, frame) -> bool:
    """True, gdy bateria właśnie stała się słaba: push raz, a nie przy każdej ramce.

    Słaba = poniżej `battery_low_pct` albo flaga z heartbeatu (firmware ma własny próg).
    Znowu dobra dopiero od progu + `BATTERY_HYSTERESIS_PCT`, żeby 19/20/19 % nie budziło co chwilę.
    """
    flagged = isinstance(frame, HeartbeatFrame) and frame.low_battery
    if frame.battery_pct < settings.battery_low_pct or flagged:
        if sensor.low_battery_notified:
            return False
        sensor.low_battery_notified = True
        return True
    if frame.battery_pct >= settings.battery_low_pct + BATTERY_HYSTERESIS_PCT:
        sensor.low_battery_notified = False
    return False


async def _is_muted(session: AsyncSession, sensor: Sensor, at: datetime) -> bool:
    """Czujnik wyłączony albo trwa wydanie drewna."""
    if not sensor.active:
        return True
    release = await session.scalar(
        select(Release.id).where(
            Release.sensor_id == sensor.id,
            Release.starts_at <= at,
            Release.ends_at > at,
        ).limit(1)
    )
    return release is not None


async def _handle_alarm(
    session: AsyncSession, sensor: Sensor, frame: AlarmFrame, at: datetime
) -> tuple[Alarm, bool]:
    """Scala powtórzenia (ALARM wysyłany 3x) w jeden alarm. Zwraca (alarm, czy_nowy)."""
    window_start = at - timedelta(seconds=settings.alarm_merge_window_s)
    alarm = await session.scalar(
        select(Alarm)
        .where(
            Alarm.sensor_id == sensor.id,
            Alarm.status == "new",
            Alarm.last_frame_at >= window_start,
        )
        .order_by(Alarm.last_frame_at.desc())
        .limit(1)
    )

    if alarm is not None:
        alarm.repeats += 1
        # replace(tzinfo): SQLite w testach zwraca daty bez strefy, wszystko i tak jest w UTC
        alarm.last_frame_at = max(alarm.last_frame_at.replace(tzinfo=at.tzinfo), at)
        alarm.confidence = max(alarm.confidence, frame.confidence)
        alarm.duration_s = max(alarm.duration_s, frame.duration_s)
        alarm.energy = max(alarm.energy, frame.energy)
        alarm.sources = sorted(set(alarm.sources) | set(frame.sources))
        return alarm, False

    alarm = Alarm(
        sensor_id=sensor.id,
        started_at=at,
        last_frame_at=at,
        event_type=frame.event_type,
        sources=frame.sources,
        confidence=frame.confidence,
        duration_s=frame.duration_s,
        energy=frame.energy,
    )
    session.add(alarm)
    return alarm, True


async def ingest(
    session: AsyncSession,
    device: str,
    payload_hex: str,
    received_at: datetime,
    rssi: int | None,
) -> IngestResult:
    frame = decode_hex(payload_hex)  # FrameError leci wyżej -> 422

    sensor = await session.get(Sensor, device)
    if sensor is None:
        raise UnknownSensorError(device)

    header = frame.header
    if is_duplicate(sensor.last_counter, header.counter, header.msg_type):
        log.info("Duplikat z %s: licznik %s (ostatni %s)", device, header.counter, sensor.last_counter)
        return IngestResult(status="duplicate")

    if sensor.last_counter is not None and header.msg_type is not MsgType.BOOT:
        lost = (header.counter - sensor.last_counter) % COUNTER_MOD - 1
        if lost > 0:
            log.warning("Czujnik %s: zgubione ramki: %s", device, lost)

    message = Message(
        received_at=received_at,
        sensor_id=sensor.id,
        msg_type=header.msg_type.name,
        counter=header.counter,
        payload_hex=payload_hex.lower(),
        decoded=to_dict(frame),
        rssi=rssi,
    )
    session.add(message)

    sensor.last_seen = received_at
    sensor.last_counter = header.counter
    sensor.battery_pct = frame.battery_pct  # każdy typ ramki niesie baterię
    sensor.silent_notified = False  # jest kontakt, więc następna cisza znów da push

    result = IngestResult(status="stored")
    result.low_battery_push = _track_battery(sensor, frame)

    if isinstance(frame, AlarmFrame):
        if await _is_muted(session, sensor, received_at):
            log.info("Alarm z %s pominięty: czujnik wyciszony/wyłączony", device)
            result.muted = True
        else:
            alarm, created = await _handle_alarm(session, sensor, frame, received_at)
            result.alarm_created = created
            await session.flush()
            result.alarm_id = alarm.id

    await session.commit()
    result.message_id = message.id
    return result
