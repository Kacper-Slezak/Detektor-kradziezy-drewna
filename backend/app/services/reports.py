"""Raporty dla nadleśniczego: podsumowanie okresu i eksport CSV (api.md, sekcja 5).

Okres to dni kalendarzowe w UTC, od `from` 00:00 do końca dnia `to` włącznie. Alarm należy
do okresu według `started_at`, wydanie według `starts_at`. Liczby czujników (`sensors`) opisują
stan z chwili zapytania, nie z okresu.
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alarm, Range, Release, Sensor
from app.services.sensors import as_utc, sensor_statuses

LOW_BATTERY_PCT = 20  # jak na mapie: poniżej 20% na czerwono
MAX_PERIOD_DAYS = 366

ALARM_STATUS_PL = {"new": "nowy", "theft": "kradzież", "false_alarm": "fałszywy alarm"}
SOURCE_PL = {"microphone": "dźwięk", "vibration": "wibracje"}

CSV_HEADER = [
    "typ",
    "id",
    "czujnik_id",
    "czujnik",
    "leśnictwo",
    "start (UTC)",
    "koniec (UTC)",
    "status",
    "pewność %",
    "źródła",
    "powtórzenia",
    "odpowiedź: kto",
    "odpowiedź: kiedy (UTC)",
    "komentarz",
    "przewoźnik",
    "liczba kłód",
    "utworzył",
]


@dataclass
class Period:
    start: date
    end: date  # włącznie

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.start, time.min, UTC)

    @property
    def end_dt(self) -> datetime:
        """Początek dnia po `end`, do porównań `< end_dt`."""
        return datetime.combine(self.end + timedelta(days=1), time.min, UTC)


def check_period(start: date, end: date) -> str | None:
    """Komunikat błędu albo None, gdy okres jest poprawny."""
    if end < start:
        return "Data „to” nie może być wcześniejsza niż „from”"
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        return f"Okres może mieć najwyżej {MAX_PERIOD_DAYS} dni"
    return None


def week_label(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def weeks_in(period: Period) -> list[str]:
    """Tygodnie ISO od `start` do `end` po kolei, także puste (wykres bez dziur)."""
    labels: list[str] = []
    day = period.start
    while day <= period.end:
        label = week_label(day)
        if not labels or labels[-1] != label:
            labels.append(label)
        day += timedelta(days=1)
    return labels


async def summary(
    session: AsyncSession, period: Period, now: datetime | None = None
) -> dict:
    now = now or datetime.now(UTC)
    alarms = (
        await session.execute(
            select(Alarm.sensor_id, Alarm.started_at, Alarm.status).where(
                Alarm.started_at >= period.start_dt, Alarm.started_at < period.end_dt
            )
        )
    ).all()
    releases = (
        await session.execute(
            select(Release.sensor_id).where(
                Release.starts_at >= period.start_dt, Release.starts_at < period.end_dt
            )
        )
    ).all()
    sensors = list((await session.scalars(select(Sensor))).all())
    states = await sensor_statuses(session, sensors, now)

    per_sensor: dict[str, dict] = {}
    for s in sensors:
        mounted = s.lat is not None and s.lon is not None
        per_sensor[s.id] = {
            "sensor_id": s.id,
            "name": s.name,
            "alarms": 0,
            "theft": 0,
            "false_alarm": 0,
            "releases": 0,
            "_mounted": mounted,
        }
    per_week = {
        label: {"week": label, "alarms": 0, "theft": 0} for label in weeks_in(period)
    }

    for sensor_id, started_at, status in alarms:
        row = per_sensor[sensor_id]
        row["alarms"] += 1
        week = per_week[week_label(as_utc(started_at).date())]
        week["alarms"] += 1
        if status == "theft":
            row["theft"] += 1
            week["theft"] += 1
        elif status == "false_alarm":
            row["false_alarm"] += 1
    for (sensor_id,) in releases:
        per_sensor[sensor_id]["releases"] += 1

    mounted = [s for s in sensors if per_sensor[s.id]["_mounted"]]
    rows = [
        r for r in per_sensor.values() if r["_mounted"] or r["alarms"] or r["releases"]
    ]
    rows.sort(key=lambda r: (-r["alarms"], r["name"] or "", r["sensor_id"]))
    for r in rows:
        del r["_mounted"]

    return {
        "period": {"from": period.start, "to": period.end},
        "alarms": {
            "total": len(alarms),
            "theft": sum(1 for a in alarms if a.status == "theft"),
            "false_alarm": sum(1 for a in alarms if a.status == "false_alarm"),
            "unanswered": sum(1 for a in alarms if a.status == "new"),
        },
        "releases": len(releases),
        "sensors": {
            "total": len(mounted),
            "silent": sum(1 for s in mounted if states[s.id].state == "silent"),
            "low_battery": sum(
                1
                for s in mounted
                if s.battery_pct is not None and s.battery_pct < LOW_BATTERY_PCT
            ),
        },
        "per_sensor": rows,
        "per_week": list(per_week.values()),
    }


def _cell(value):
    """Komórka CSV. Tekst zaczynający się od = + - @ Excel wykonałby jak formułę (CSV injection,
    OWASP), a komentarze i nazwy wpisują użytkownicy, więc przed takim tekstem dajemy apostrof."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return "" if value is None else value


def _ts(value: datetime | None) -> str:
    value = as_utc(value)
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


async def export_csv(
    session: AsyncSession, period: Period, now: datetime | None = None
) -> str:
    """Alarmy i wydania w jednej tabeli, od najstarszego. UTF-8 z BOM i `;` (Excel po polsku)."""
    now = now or datetime.now(UTC)
    alarms = (
        await session.execute(
            select(Alarm, Sensor, Range.name)
            .join(Sensor, Alarm.sensor_id == Sensor.id)
            .outerjoin(Range, Sensor.range_id == Range.id)
            .where(
                Alarm.started_at >= period.start_dt, Alarm.started_at < period.end_dt
            )
        )
    ).all()
    releases = (
        await session.execute(
            select(Release, Sensor, Range.name)
            .join(Sensor, Release.sensor_id == Sensor.id)
            .outerjoin(Range, Sensor.range_id == Range.id)
            .where(
                Release.starts_at >= period.start_dt, Release.starts_at < period.end_dt
            )
        )
    ).all()

    records: list[tuple[datetime, int, list]] = []
    for a, s, range_name in alarms:
        records.append(
            (
                as_utc(a.started_at),
                a.id,
                [
                    "alarm",
                    a.id,
                    s.id,
                    s.name,
                    range_name,
                    _ts(a.started_at),
                    _ts(a.last_frame_at),
                    ALARM_STATUS_PL.get(a.status, a.status),
                    a.confidence,
                    ", ".join(SOURCE_PL.get(x, x) for x in a.sources),
                    a.repeats,
                    a.response_by,
                    _ts(a.response_at),
                    a.response_comment,
                    None,
                    None,
                    None,
                ],
            )
        )
    for r, s, range_name in releases:
        active = as_utc(r.starts_at) <= now < as_utc(r.ends_at)
        records.append(
            (
                as_utc(r.starts_at),
                r.id,
                [
                    "wydanie",
                    r.id,
                    s.id,
                    s.name,
                    range_name,
                    _ts(r.starts_at),
                    _ts(r.ends_at),
                    "trwa" if active else "zakończone",
                    None,
                    None,
                    None,
                    None,
                    None,
                    r.comment,
                    r.carrier,
                    r.log_count,
                    r.created_by,
                ],
            )
        )
    records.sort(key=lambda rec: (rec[0], rec[2][0], rec[1]))

    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for _, _, row in records:
        writer.writerow([_cell(v) for v in row])
    return "﻿" + out.getvalue()
