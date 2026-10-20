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
    MsgType,
    decode_hex,
    to_dict,
)

log = logging.getLogger(__name__)

COUNTER_MOD = 1 << 16  # licznik ma 2 B i się przekręca


class UnknownSensorError(Exception):
    pass


@dataclass
class IngestResult:
    status: str  # "stored" albo "duplicate"
    message_id: int | None = None
    alarm_id: int | None = None
    alarm_created: bool = False
    muted: bool = False


def is_duplicate(last_counter: int | None, counter: int, msg_type: MsgType) -> bool:
    """Ramka z licznikiem nie większym niż ostatni = duplikat albo stara ramka.

    Po BOOT licznik może zacząć od nowa, więc go akceptujemy.
    Uwzględnia przekręcenie 65535 -> 0.
    """
    if last_counter is None or msg_type is MsgType.BOOT:
        return False
    diff = (counter - last_counter) % COUNTER_MOD
    return diff == 0 or diff > COUNTER_MOD // 2


async def _is_muted(session: AsyncSession, sensor: Sensor, at: datetime) -> bool:
    """Czujnik wyłączony albo trwa wydanie drewna."""
    if not sensor.active:
        return True
    release = await session.scalar(
        select(Release.id).where(
            Release.sensor_id == sensor.id,
            Release.starts_at <= at,
            Release.ends_at >= at,
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


