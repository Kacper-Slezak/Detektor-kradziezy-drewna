"""Raporty dla nadleśniczego (api.md, sekcja 5)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_role
from app.models import User
from app.services import reports
from app.services.reports import Period

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Session = Annotated[AsyncSession, Depends(get_session)]
Manager = Annotated[User, Depends(require_role("district_manager", "admin"))]
From = Annotated[
    date, Query(alias="from", description="Pierwszy dzień okresu (UTC), RRRR-MM-DD")
]
To = Annotated[date, Query(description="Ostatni dzień okresu (UTC), włącznie")]


class PeriodOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: date = Field(alias="from")
    to: date


class AlarmCounts(BaseModel):
    total: int
    theft: int
    false_alarm: int
    unanswered: int


class SensorCounts(BaseModel):
    total: int
    silent: int
    low_battery: int


class SensorRow(BaseModel):
    sensor_id: str
    name: str | None
    alarms: int
    theft: int
    false_alarm: int
    releases: int


class WeekRow(BaseModel):
    week: str
    alarms: int
    theft: int


class SummaryOut(BaseModel):
    period: PeriodOut
    alarms: AlarmCounts
    releases: int
    sensors: SensorCounts
    per_sensor: list[SensorRow]
    per_week: list[WeekRow]


def _period(start: date, end: date) -> Period:
    error = reports.check_period(start, end)
    if error:
        raise HTTPException(422, error)
    return Period(start, end)


@router.get(
    "/summary",
    response_model=SummaryOut,
    responses={
        403: {"description": "Tylko nadleśniczy i admin"},
        422: {
            "description": "Zły okres: brak dat, `to` przed `from` albo ponad 366 dni"
        },
    },
)
async def summary(_: Manager, session: Session, from_: From, to: To) -> SummaryOut:
    data = await reports.summary(session, _period(from_, to))
    return SummaryOut.model_validate(data)


@router.get(
    "/export.csv",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Alarmy i wydania z okresu (CSV)",
        },
        403: {"description": "Tylko nadleśniczy i admin"},
        422: {"description": "Zły okres"},
    },
)
async def export_csv(_: Manager, session: Session, from_: From, to: To) -> Response:
    period = _period(from_, to)
    content = await reports.export_csv(session, period)
    filename = f"raport-{period.start.isoformat()}_{period.end.isoformat()}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
