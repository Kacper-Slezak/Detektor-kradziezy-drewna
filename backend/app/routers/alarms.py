"""Alarmy: lista, szczegóły i odpowiedź leśniczego (api.md, sekcja 4).

Kto co może:
- lista i szczegóły: leśniczy swoje leśnictwo (cudzy alarm → 403), nadleśniczy i admin wszystko,
- odpowiedź: leśniczy swojego leśnictwa i admin (np. poprawka); nadleśniczy tylko czyta.

Odpowiedź nie idzie do czujnika (łączność jednostronna): zamyka alarm i jest etykietą dla Kiryla.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import CurrentUser, require_role
from app.models import Alarm, Sensor, User
from app.schemas import (
    EVENT_TYPES,
    AlarmOut,
    AlarmResponse,
    AlarmResponseIn,
    AlarmSensor,
    AlarmStatus,
    normalize_sensor_id,
)
from app.scope import check_range_access, range_filter
from app.services.sensors import as_utc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/alarms", tags=["alarms"])

Session = Annotated[AsyncSession, Depends(get_session)]
Responder = Annotated[User, Depends(require_role("forester", "admin"))]

OTHER_RANGE = "Alarm dotyczy czujnika z innego leśnictwa"


def _to_out(alarm: Alarm, sensor: Sensor) -> AlarmOut:
    response = None
    if alarm.response_by is not None:
        response = AlarmResponse(
            by=alarm.response_by,
            at=as_utc(alarm.response_at),
            comment=alarm.response_comment,
            lat=alarm.response_lat,
            lon=alarm.response_lon,
        )
    return AlarmOut(
        id=alarm.id,
        detected_at=as_utc(alarm.started_at),
        last_frame_at=as_utc(alarm.last_frame_at),
        sensor=AlarmSensor(id=sensor.id, name=sensor.name, lat=sensor.lat, lon=sensor.lon),
        event_type=EVENT_TYPES.get(alarm.event_type, "unknown"),
        sources=alarm.sources,
        confidence=alarm.confidence,
        duration_s=alarm.duration_s,
        energy=alarm.energy,
        repeats=alarm.repeats,
        # same wibracje bez dźwięku: raczej ktoś przy czujniku niż kradzież
        possible_tampering=alarm.sources == ["vibration"],
        status=alarm.status,
        response=response,
    )


def _with_sensor() -> Select:
    return select(Alarm, Sensor).join(Sensor, Alarm.sensor_id == Sensor.id)


def _utc(value: datetime | None) -> datetime | None:
    """Czas bez strefy w parametrach traktujemy jako UTC (jak w całym API)."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


async def _get(session: AsyncSession, alarm_id: int, user: User) -> tuple[Alarm, Sensor]:
    row = (await session.execute(_with_sensor().where(Alarm.id == alarm_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nie ma alarmu o id {alarm_id}")
    alarm, sensor = row
    check_range_access(sensor.range_id, user, OTHER_RANGE)
    return alarm, sensor


@router.get("", response_model=list[AlarmOut])
async def list_alarms(
    user: CurrentUser,
    session: Session,
    status_: Annotated[AlarmStatus | None, Query(alias="status")] = None,
    sensor_id: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from", description="Wykryte od (UTC)")] = None,
    to: Annotated[datetime | None, Query(description="Wykryte do (UTC)")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AlarmOut]:
    query = _with_sensor()
    condition = range_filter(user)
    if condition is not None:
        query = query.where(condition)
    if status_ is not None:
        query = query.where(Alarm.status == status_)
    if sensor_id is not None:
        query = query.where(Alarm.sensor_id == normalize_sensor_id(sensor_id))
    if from_ is not None:
        query = query.where(Alarm.started_at >= _utc(from_))
    if to is not None:
        query = query.where(Alarm.started_at <= _utc(to))
    query = query.order_by(Alarm.started_at.desc(), Alarm.id.desc()).limit(limit).offset(offset)

    rows = await session.execute(query)
    return [_to_out(alarm, sensor) for alarm, sensor in rows]


@router.get(
    "/{alarm_id}",
    response_model=AlarmOut,
    responses={403: {"description": OTHER_RANGE}, 404: {"description": "Brak alarmu"}},
)
async def get_alarm(alarm_id: int, user: CurrentUser, session: Session) -> AlarmOut:
    alarm, sensor = await _get(session, alarm_id, user)
    return _to_out(alarm, sensor)


@router.post(
    "/{alarm_id}/response",
    response_model=AlarmOut,
    responses={
        403: {"description": "Nadleśniczy albo alarm z innego leśnictwa"},
        404: {"description": "Brak alarmu"},
        409: {"description": "Alarm ma już odpowiedź"},
    },
)
async def respond(
    alarm_id: int, body: AlarmResponseIn, user: Responder, session: Session
) -> AlarmOut:
    alarm, sensor = await _get(session, alarm_id, user)
    if alarm.status != "new":
        raise HTTPException(status.HTTP_409_CONFLICT, "Alarm ma już odpowiedź")

    # warunek status = 'new' w samym UPDATE: dwóch leśniczych naraz nie nadpisze sobie odpowiedzi
    result = await session.execute(
        update(Alarm)
        .where(Alarm.id == alarm.id, Alarm.status == "new")
        .values(
            status=body.result,
            response_by=user.login,
            response_at=datetime.now(UTC),
            response_comment=body.comment,
            response_lat=body.lat,
            response_lon=body.lon,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Alarm ma już odpowiedź")
    await session.commit()
    await session.refresh(alarm)
    log.info("%s odpowiedział na alarm %s: %s", user.login, alarm.id, body.result)
    return _to_out(alarm, sensor)
