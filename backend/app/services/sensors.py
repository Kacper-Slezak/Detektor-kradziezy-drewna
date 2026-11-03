"""Stan czujnika dla mapy i panelu admina.

Nie trzymamy go w bazie, tylko liczymy przy każdym odczycie z czterech rzeczy:
czy czujnik jest włączony i zamontowany, otwartych alarmów, trwających wydań i `last_seen`.
Dzięki temu stan nigdy się nie rozjedzie z danymi (np. wydanie samo się kończy).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Alarm, Release, Sensor


@dataclass
class SensorStatus:
    state: str
    open_alarm_id: int | None
    muted_until: datetime | None


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite (testy) zwraca czas bez strefy; zapisujemy zawsze UTC, więc ją doklejamy."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def compute_state(
    sensor: Sensor,
    *,
    open_alarm_id: int | None,
    muted_until: datetime | None,
    now: datetime,
) -> str:
    """Kolejność ma znaczenie: inactive → alarm → muted → silent → ok.

    - inactive: wyłączony w apce albo jeszcze niezamontowany (brak lokalizacji)
    - alarm: jest alarm bez odpowiedzi leśniczego, nawet jeśli potem zaczęło się wydanie
    - muted: trwa wydanie drewna
    - silent: brak ramki dłużej niż `sensor_silent_after_h` albo czujnik nigdy się nie odezwał
    """
    if not sensor.active or sensor.lat is None or sensor.lon is None:
        return "inactive"
    if open_alarm_id is not None:
        return "alarm"
    if muted_until is not None:
        return "muted"
    last_seen = as_utc(sensor.last_seen)
    if last_seen is None or now - last_seen > timedelta(
        hours=settings.sensor_silent_after_h
    ):
        return "silent"
    return "ok"


async def sensor_statuses(
    session: AsyncSession, sensors: list[Sensor], now: datetime | None = None
) -> dict[str, SensorStatus]:
    """Stany dla całej listy: 2 zapytania niezależnie od liczby czujników (bez N+1)."""
    now = now or datetime.now(UTC)
    ids = [s.id for s in sensors]
    open_alarms: dict[str, int] = {}
    muted: dict[str, datetime] = {}

    if ids:
        rows = await session.execute(
            select(Alarm.sensor_id, func.max(Alarm.id))
            .where(Alarm.sensor_id.in_(ids), Alarm.status == "new")
            .group_by(Alarm.sensor_id)
        )
        open_alarms = {sensor_id: alarm_id for sensor_id, alarm_id in rows}

        # te same warunki co przy wyciszaniu w /ingest
        rows = await session.execute(
            select(Release.sensor_id, func.max(Release.ends_at))
            .where(
                Release.sensor_id.in_(ids),
                Release.starts_at <= now,
                Release.ends_at >= now,
            )
            .group_by(Release.sensor_id)
        )
        muted = {sensor_id: as_utc(ends_at) for sensor_id, ends_at in rows}

    result = {}
    for sensor in sensors:
        alarm_id = open_alarms.get(sensor.id)
        muted_until = muted.get(sensor.id)
        result[sensor.id] = SensorStatus(
            state=compute_state(
                sensor, open_alarm_id=alarm_id, muted_until=muted_until, now=now
            ),
            open_alarm_id=alarm_id,
            muted_until=muted_until,
        )
    return result
