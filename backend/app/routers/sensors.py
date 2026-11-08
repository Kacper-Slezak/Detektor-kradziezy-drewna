"""Czujniki: lista na mapę i do panelu admina, szczegóły, rejestracja, edycja (api.md, sekcja 2).

Kto co widzi:
- leśniczy: tylko czujniki swojego leśnictwa (cudzy czujnik → 403),
- nadleśniczy i admin: wszystkie.

Kto co zmienia:
- admin: rejestruje czujniki, zmienia nazwę, leśnictwo, włącza/wyłącza, montuje (poprawki),
- leśniczy: montuje, zmienia nazwę i włącza/wyłącza czujniki swojego leśnictwa,
- nadleśniczy: tylko odczyt.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import AdminUser, CurrentUser, require_role
from app.models import Alarm, Range, Release, Sensor, User
from app.schemas import (
    AlarmBrief,
    ReleaseBrief,
    SensorCreate,
    SensorDetailOut,
    SensorMount,
    SensorOut,
    SensorPatch,
    SensorState,
    normalize_sensor_id,
)
from app.scope import check_range_access, range_filter
from app.services.sensors import SensorStatus, as_utc, sensor_statuses

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sensors", tags=["sensors"])

Session = Annotated[AsyncSession, Depends(get_session)]
SensorEditor = Annotated[User, Depends(require_role("forester", "admin"))]

RECENT_LIMIT = 5


def _scoped(query: Select, user: User) -> Select:
    condition = range_filter(user)
    return query if condition is None else query.where(condition)


async def _get_sensor(session: AsyncSession, sensor_id: str, user: User) -> Sensor:
    sensor = await session.get(Sensor, normalize_sensor_id(sensor_id))
    if sensor is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Czujnik o id {sensor_id} nie istnieje"
        )
    check_range_access(sensor.range_id, user, "Czujnik należy do innego leśnictwa")
    return sensor


async def _check_range(session: AsyncSession, range_id: int) -> None:
    if await session.get(Range, range_id) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Nie ma leśnictwa o id {range_id}"
        )


def _to_out(sensor: Sensor, st: SensorStatus) -> SensorOut:
    return SensorOut(
        id=sensor.id,
        name=sensor.name,
        lat=sensor.lat,
        lon=sensor.lon,
        range_id=sensor.range_id,
        active=sensor.active,
        state=st.state,
        battery_pct=sensor.battery_pct,
        last_seen=as_utc(sensor.last_seen),
        muted_until=st.muted_until,
        open_alarm_id=st.open_alarm_id,
    )


async def _one_out(session: AsyncSession, sensor: Sensor) -> SensorOut:
    statuses = await sensor_statuses(session, [sensor])
    return _to_out(sensor, statuses[sensor.id])


@router.get("", response_model=list[SensorOut])
async def list_sensors(
    user: CurrentUser,
    session: Session,
    state: Annotated[
        SensorState | None, Query(description="Tylko czujniki w tym stanie")
    ] = None,
    range_id: Annotated[int | None, Query(description="Tylko to leśnictwo")] = None,
    unmounted: Annotated[
        bool, Query(description="Tylko czujniki bez lokalizacji (do montażu)")
    ] = False,
) -> list[SensorOut]:
    query = _scoped(select(Sensor), user).order_by(Sensor.range_id, Sensor.id)
    if range_id is not None:
        query = query.where(Sensor.range_id == range_id)
    if unmounted:
        query = query.where((Sensor.lat.is_(None)) | (Sensor.lon.is_(None)))

    sensors = list((await session.scalars(query)).all())
    statuses = await sensor_statuses(session, sensors)
    out = [_to_out(s, statuses[s.id]) for s in sensors]
    # stan jest liczony, a nie zapisany w bazie, więc filtrujemy po wyliczeniu
    if state is not None:
        out = [s for s in out if s.state == state]
    return out


@router.get(
    "/{sensor_id}",
    response_model=SensorDetailOut,
    responses={
        403: {"description": "Czujnik z innego leśnictwa"},
        404: {"description": "Brak czujnika"},
    },
)
async def get_sensor(
    sensor_id: str, user: CurrentUser, session: Session
) -> SensorDetailOut:
    sensor = await _get_sensor(session, sensor_id, user)
    base = await _one_out(session, sensor)

    alarms = await session.scalars(
        select(Alarm)
        .where(Alarm.sensor_id == sensor.id)
        .order_by(Alarm.started_at.desc())
        .limit(RECENT_LIMIT)
    )
    releases = await session.scalars(
        select(Release)
        .where(Release.sensor_id == sensor.id)
        .order_by(Release.starts_at.desc())
        .limit(RECENT_LIMIT)
    )
    return SensorDetailOut(
        **base.model_dump(),
        recent_alarms=[
            AlarmBrief(
                id=a.id,
                detected_at=as_utc(a.started_at),
                status=a.status,
                confidence=a.confidence,
            )
            for a in alarms
        ],
        recent_releases=[
            ReleaseBrief(
                id=r.id,
                starts_at=as_utc(r.starts_at),
                ends_at=as_utc(r.ends_at),
                carrier=r.carrier,
                log_count=r.log_count,
            )
            for r in releases
        ],
    )


@router.post(
    "",
    response_model=SensorOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Nie ma leśnictwa"},
        409: {"description": "Czujnik już dodany"},
    },
)
async def create_sensor(
    body: SensorCreate, admin: AdminUser, session: Session
) -> SensorOut:
    if await session.get(Sensor, body.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Czujnik {body.id} jest już dodany"
        )
    await _check_range(session, body.range_id)

    # nieaktywny i bez lokalizacji, aż leśniczy go zamontuje (PUT /sensors/{id}/mount)
    sensor = Sensor(id=body.id, name=body.name, range_id=body.range_id, active=False)
    session.add(sensor)
    try:
        await session.commit()
    except IntegrityError:  # ktoś dodał ten sam czujnik w międzyczasie
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Czujnik {body.id} jest już dodany"
        ) from None
    log.info(
        "Admin %s dodał czujnik %s (leśnictwo %s)",
        admin.login,
        sensor.id,
        sensor.range_id,
    )
    return await _one_out(session, sensor)


@router.patch(
    "/{sensor_id}",
    response_model=SensorOut,
    responses={
        400: {"description": "Nie ma leśnictwa"},
        403: {"description": "Brak uprawnień albo czujnik z innego leśnictwa"},
        404: {"description": "Brak czujnika"},
    },
)
async def update_sensor(
    sensor_id: str, body: SensorPatch, user: SensorEditor, session: Session
) -> SensorOut:
    sensor = await _get_sensor(session, sensor_id, user)
    changes = body.model_dump(exclude_unset=True)

    if "range_id" in changes:
        if user.role != "admin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Tylko admin może zmienić leśnictwo"
            )
        await _check_range(session, changes["range_id"])

    for field, value in changes.items():
        setattr(sensor, field, value)
    await session.commit()
    log.info("%s zmienił czujnik %s: %s", user.login, sensor.id, sorted(changes))
    return await _one_out(session, sensor)


@router.put(
    "/{sensor_id}/mount",
    response_model=SensorOut,
    responses={
        403: {"description": "Nadleśniczy albo czujnik z innego leśnictwa"},
        404: {"description": "Brak czujnika"},
    },
)
async def mount_sensor(
    sensor_id: str, body: SensorMount, user: SensorEditor, session: Session
) -> SensorOut:
    """Leśniczy przy stosie drewna: nazwa + GPS z telefonu, czujnik zaczyna czuwać.

    Ponowny montaż (przeniesienie czujnika) nadpisuje nazwę i lokalizację.
    """
    sensor = await _get_sensor(session, sensor_id, user)
    remount = sensor.lat is not None and sensor.lon is not None
    sensor.name = body.name
    sensor.lat = body.lat
    sensor.lon = body.lon
    sensor.active = True
    await session.commit()
    log.info(
        "%s %s czujnik %s: %s (%.5f, %.5f)",
        user.login,
        "przeniósł" if remount else "zamontował",
        sensor.id,
        sensor.name,
        sensor.lat,
        sensor.lon,
    )
    return await _one_out(session, sensor)
