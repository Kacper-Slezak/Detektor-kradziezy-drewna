"""Wydania drewna, czyli wyciszanie czujnika na czas legalnego wywozu (api.md, sekcja 3).

W trakcie wydania /ingest zapisuje ramki, ale nie tworzy alarmów (`_is_muted` w services/ingest.py),
a czujnik ma stan `muted`. Wydanie zaczyna się „teraz” i kończy o `ends_at` albo wcześniej,
gdy leśniczy je zakończy.

Kto co może:
- tworzy i kończy: leśniczy swojego leśnictwa, admin (poprawki),
- historia: leśniczy swoje leśnictwo, nadleśniczy i admin wszystko.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.deps import CurrentUser, require_role
from app.models import Release, Sensor, User
from app.schemas import ReleaseCreate, ReleaseOut, normalize_sensor_id
from app.scope import check_range_access, range_filter
from app.services.sensors import as_utc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["releases"])

Session = Annotated[AsyncSession, Depends(get_session)]
Releaser = Annotated[User, Depends(require_role("forester", "admin"))]

OTHER_RANGE = "Czujnik należy do innego leśnictwa"


def _to_out(release: Release, sensor: Sensor, now: datetime) -> ReleaseOut:
    starts_at, ends_at = as_utc(release.starts_at), as_utc(release.ends_at)
    return ReleaseOut(
        id=release.id,
        sensor_id=release.sensor_id,
        sensor_name=sensor.name,
        starts_at=starts_at,
        ends_at=ends_at,
        active=starts_at <= now < ends_at,
        carrier=release.carrier,
        log_count=release.log_count,
        comment=release.comment,
        created_by=release.created_by,
    )


def _with_sensor() -> Select:
    return select(Release, Sensor).join(Sensor, Release.sensor_id == Sensor.id)


@router.post(
    "/sensors/{sensor_id}/releases",
    response_model=ReleaseOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Nadleśniczy albo czujnik z innego leśnictwa"},
        404: {"description": "Brak czujnika"},
        409: {"description": "Czujnik niezamontowany albo wydanie dla niego już trwa"},
        422: {"description": "Koniec w przeszłości albo za daleko w przyszłości"},
    },
)
async def create_release(
    sensor_id: str, body: ReleaseCreate, user: Releaser, session: Session
) -> ReleaseOut:
    # FOR UPDATE na wierszu czujnika: dwa równoczesne zapytania o wydanie dla tego samego
    # czujnika idą po kolei, więc drugie zobaczy pierwsze wydanie i dostanie 409
    # (Postgres; SQLite w testach ignoruje blokadę).
    sensor = await session.get(
        Sensor, normalize_sensor_id(sensor_id), with_for_update=True
    )
    if sensor is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Czujnik o id {sensor_id} nie istnieje"
        )
    check_range_access(sensor.range_id, user, OTHER_RANGE)
    if sensor.lat is None or sensor.lon is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Czujnik nie jest zamontowany (brak lokalizacji)",
        )

    now = datetime.now(UTC)
    # czas bez strefy = UTC (jak w całym API)
    ends_at = as_utc(body.ends_at) or now + timedelta(
        hours=settings.release_default_hours
    )
    if ends_at <= now:
        raise HTTPException(422, "Koniec wydania musi być w przyszłości")
    if ends_at > now + timedelta(hours=settings.release_max_hours):
        raise HTTPException(
            422,
            f"Wydanie może trwać najwyżej {settings.release_max_hours} h",
        )

    ongoing = await session.scalar(
        select(Release.id).where(
            Release.sensor_id == sensor.id,
            Release.starts_at <= now,
            Release.ends_at > now,
        )
    )
    if ongoing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Wydanie dla tego czujnika już trwa (id {ongoing}); zakończ je albo poczekaj",
        )

    release = Release(
        sensor_id=sensor.id,
        starts_at=now,
        ends_at=ends_at,
        carrier=body.carrier,
        log_count=body.log_count,
        comment=body.comment,
        created_by=user.login,
    )
    session.add(release)
    await session.commit()
    log.info(
        "%s wydał drewno z czujnika %s do %s (przewoźnik: %s)",
        user.login,
        sensor.id,
        ends_at.isoformat(timespec="minutes"),
        release.carrier or "-",
    )
    return _to_out(release, sensor, now)


@router.post(
    "/releases/{release_id}/end",
    response_model=ReleaseOut,
    responses={
        403: {"description": "Nadleśniczy albo wydanie z innego leśnictwa"},
        404: {"description": "Brak wydania"},
        409: {"description": "Wydanie już się zakończyło"},
    },
)
async def end_release(release_id: int, user: Releaser, session: Session) -> ReleaseOut:
    """Przewoźnik odjechał wcześniej: koniec wyciszenia od razu."""
    row = (
        await session.execute(_with_sensor().where(Release.id == release_id))
    ).first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Nie ma wydania o id {release_id}"
        )
    release, sensor = row
    check_range_access(sensor.range_id, user, OTHER_RANGE)

    now = datetime.now(UTC)
    if as_utc(release.ends_at) <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wydanie już się zakończyło")
    release.ends_at = now
    await session.commit()
    log.info("%s zakończył wydanie %s (czujnik %s)", user.login, release.id, sensor.id)
    return _to_out(release, sensor, now)


@router.get("/releases", response_model=list[ReleaseOut])
async def list_releases(
    user: CurrentUser,
    session: Session,
    sensor_id: str | None = None,
    active: Annotated[bool | None, Query(description="true = tylko trwające")] = None,
    from_: Annotated[
        datetime | None,
        Query(alias="from", description="Wydania trwające po tej chwili (UTC)"),
    ] = None,
    to: Annotated[
        datetime | None, Query(description="Wydania zaczęte przed tą chwilą (UTC)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReleaseOut]:
    now = datetime.now(UTC)
    query = _with_sensor()
    condition = range_filter(user)
    if condition is not None:
        query = query.where(condition)
    if sensor_id is not None:
        query = query.where(Release.sensor_id == normalize_sensor_id(sensor_id))
    if active is True:
        query = query.where(Release.starts_at <= now, Release.ends_at > now)
    elif active is False:
        query = query.where((Release.ends_at <= now) | (Release.starts_at > now))
    # przedział [from, to] i wydanie zachodzą na siebie
    if from_ is not None:
        query = query.where(Release.ends_at >= as_utc(from_))
    if to is not None:
        query = query.where(Release.starts_at <= as_utc(to))
    query = (
        query.order_by(Release.starts_at.desc(), Release.id.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = await session.execute(query)
    return [_to_out(release, sensor, now) for release, sensor in rows]
