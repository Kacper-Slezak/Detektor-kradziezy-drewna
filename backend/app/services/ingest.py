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
    BootFrame,
    FrameError,
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


def is_boot_replay(last_boot_id: int | None, boot_id: int) -> bool:
    """BOOT z boot_id nie większym niż ostatni przyjęty to powtórka starego BOOT.

    Jak przy liczniku: arytmetyka modulo 2^16, więc przekręcenie 65535 -> 0 jest w porządku.
    """
    if last_boot_id is None:
        return False
    diff = (boot_id - last_boot_id) % COUNTER_MOD
    return diff == 0 or diff > COUNTER_MOD // 2


def check_boot(sensor: Sensor, frame: BootFrame) -> bool:
    """True, gdy BOOT jest powtórką (nie przyjmujemy go i nie resetujemy licznika).

    FrameError dla BOOT bez boot_id tam, gdzie to niedozwolone: gdy tak ustawiono
    (`BOOT_ID_REQUIRED`) albo gdy czujnik już używał boot_id. Inaczej stary BOOT wersji 1
    wystarczyłby, żeby zresetować licznik czujnika i powtórzyć jego dawne ramki.
    """
    if frame.boot_id is None:
        if settings.boot_id_required:
            raise FrameError("BOOT musi mieć boot_id (ramka wersji 2)")
        if sensor.last_boot_id is not None:
            raise FrameError("BOOT bez boot_id od czujnika, który wysyła boot_id")
        return False
    return is_boot_replay(sensor.last_boot_id, frame.boot_id)


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
    if isinstance(frame, BootFrame) and check_boot(sensor, frame):
        log.warning(
            "Powtórka BOOT z %s: boot_id %s (ostatni %s), licznik zostaje",
            device,
            frame.boot_id,
            sensor.last_boot_id,
        )
        return IngestResult(status="duplicate")
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
    if isinstance(frame, BootFrame) and frame.boot_id is not None:
        sensor.last_boot_id = frame.boot_id
    sensor.battery_pct = frame.battery_pct  # każdy typ ramki niesie baterię

    result = IngestResult(status="stored")

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
