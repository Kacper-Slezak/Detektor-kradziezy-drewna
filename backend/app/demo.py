"""Dane demo: leśniczy, nadleśniczy i czujniki w każdym stanie, z historią z ostatnich 7 dni.

Historia nie jest wpisywana do tabel ręcznie: każda ramka jest pakowana koderem
(tak jak w firmware) i przechodzi przez `ingest()`, czyli tę samą ścieżkę co prawdziwe dane.
Dzięki temu `messages`, `alarms`, `battery_pct`, `last_seen` i `last_counter` zawsze się zgadzają.

Czasy są liczone od "teraz", więc po kilku godzinach stany się zestarzeją
(np. "ok" przejdzie w "silent"). Wtedy: `python -m app.seed --demo --reset`.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Alarm, Message, PushSubscription, Range, Release, Sensor, User
from app.protocol.encoder import encode_alarm, encode_boot, encode_heartbeat
from app.security import hash_password
from app.services.ingest import ingest

log = logging.getLogger(__name__)

# ID czujników demo: prefiks + 4 znaki. Po prefiksie --reset wie, co usunąć.
DEMO_PREFIX = "70B3D57ED00D"
HISTORY_DAYS = 7
HEARTBEAT_EVERY = timedelta(hours=6)
REPEAT_GAP = timedelta(seconds=30)  # ALARM wysyłany 3 razy co 30 s

DABROWA = "Leśnictwo Dąbrowa"
OLSZYNY = "Leśnictwo Olszyny"

# login, imię i nazwisko, rola, leśnictwo
DEMO_USERS = [
    ("blazej", "Błażej Kowalski", "forester", DABROWA),
    ("ola", "Aleksandra Nowak", "forester", OLSZYNY),
    ("bogdan", "Bogdan Wiśniewski", "district_manager", None),
]


@dataclass
class DemoSensor:
    suffix: str
    name: str | None
    range_name: str
    lat: float | None
    lon: float | None
    # ok / alarm / muted / silent / low_battery / off / unmounted / bench
    scenario: str
    battery_start: int = 95
    extra: list[str] = field(default_factory=list)  # zdarzenia w historii

    @property
    def id(self) -> str:
        return DEMO_PREFIX + self.suffix


# Puszcza Niepołomicka: Dąbrowa na zachodzie, Olszyny na wschodzie
DEMO_SENSORS = [
    DemoSensor(
        "0001",
        "Skład przy drodze 5",
        DABROWA,
        50.0712,
        20.3105,
        "ok",
        extra=["false_alarm_3d", "release_2d"],
    ),
    DemoSensor("0002", "Skład przy szlabanie", DABROWA, 50.0655, 20.3290, "alarm"),
    DemoSensor("0003", "Skład przy stawie", DABROWA, 50.0588, 20.3187, "muted"),
    DemoSensor("0004", "Skład w oddziale 112", DABROWA, 50.0801, 20.3402, "silent"),
    DemoSensor(
        "0005",
        "Skład przy leśniczówce",
        DABROWA,
        50.0532,
        20.3011,
        "low_battery",
        battery_start=32,
    ),
    DemoSensor("0006", "Skład pusty (do zdjęcia)", DABROWA, 50.0744, 20.2954, "off"),
    DemoSensor("0007", None, DABROWA, None, None, "bench"),
    DemoSensor(
        "0008",
        "Skład przy drodze 964",
        OLSZYNY,
        50.0463,
        20.3871,
        "ok",
        extra=["theft_5d"],
    ),
    DemoSensor("0009", "Skład na Kopcu", OLSZYNY, 50.0391, 20.4105, "ok"),
    DemoSensor("000A", None, OLSZYNY, None, None, "unmounted"),
]


@dataclass
class _Frame:
    at: datetime
    payload: bytes


@dataclass
class _Closing:
    """Odpowiedź leśniczego na alarm z historii."""

    at: datetime
    status: str
    by: str
    comment: str


@dataclass
class _Plan:
    frames: list[_Frame] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    closings: list[_Closing] = field(default_factory=list)


def _burst(start: datetime, counter: int, **alarm) -> list[_Frame]:
    """ALARM wysłany 3 razy, jak w firmware. Backend scali je w jeden alarm."""
    return [
        _Frame(start + i * REPEAT_GAP, encode_alarm(counter + i, **alarm))
        for i in range(3)
    ]


def _plan(sensor: DemoSensor, now: datetime, rng: random.Random) -> _Plan:
    plan = _Plan()
    if sensor.scenario == "unmounted":
        return plan  # jeszcze nic nie wysłał
    if sensor.scenario == "bench":
        # sprawdzony na biurku: jedna ramka BOOT godzinę temu
        plan.frames.append(
            _Frame(now - timedelta(hours=1), encode_boot(0, battery_pct=100))
        )
        return plan

    start = now - timedelta(days=HISTORY_DAYS) + timedelta(minutes=rng.randint(0, 120))
    end = now - timedelta(hours=20) if sensor.scenario == "silent" else now
    battery = float(sensor.battery_start)
    counter = 0
    plan.frames.append(_Frame(start, encode_boot(counter, battery_pct=round(battery))))

    # zdarzenia: (czas, funkcja tworząca ramki dla danego licznika)
    events: list[tuple[datetime, str]] = []
    if sensor.scenario == "alarm":
        events.append((now - timedelta(minutes=25), "open_theft"))
    if sensor.scenario == "muted":
        events.append((now - timedelta(minutes=40), "muted_alarm"))
        plan.releases.append(
            Release(
                sensor_id=sensor.id,
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(hours=3),
                carrier="TransLas",
                log_count=40,
                comment="wywóz z umowy 12/2026",
                created_by="blazej",
            )
        )
    if "false_alarm_3d" in sensor.extra:
        events.append((now - timedelta(days=3, hours=2), "false_alarm"))
    if "theft_5d" in sensor.extra:
        events.append((now - timedelta(days=5, hours=4), "theft"))
    if "release_2d" in sensor.extra:
        starts = now - timedelta(days=2, hours=9)
        plan.releases.append(
            Release(
                sensor_id=sensor.id,
                starts_at=starts,
                ends_at=starts + timedelta(hours=8),
                carrier="Drewbud",
                log_count=25,
                created_by="blazej",
            )
        )

    t = start + HEARTBEAT_EVERY
    pending = sorted(events)
    while t <= end:
        while pending and pending[0][0] <= t:
            at, kind = pending.pop(0)
            frames, closing = _event(kind, at, counter + 1, round(battery), rng)
            plan.frames += frames
            counter += len(frames)
            if closing:
                plan.closings.append(closing)
        battery = max(1.0, battery - rng.uniform(0.3, 0.8))
        counter += 1
        plan.frames.append(
            _Frame(
                t,
                encode_heartbeat(
                    counter,
                    battery_pct=round(battery),
                    rejected_events=rng.randint(0, 4),
                    low_battery=battery < 20,
                ),
            )
        )
        t += HEARTBEAT_EVERY
    # zdarzenia po ostatnim heartbeacie (np. alarm sprzed 25 min)
    for at, kind in pending:
        frames, closing = _event(kind, at, counter + 1, round(battery), rng)
        plan.frames += frames
        counter += len(frames)
        if closing:
            plan.closings.append(closing)
    return plan


def _event(
    kind: str, at: datetime, counter: int, battery: int, rng: random.Random
) -> tuple[list[_Frame], _Closing | None]:
    if kind in ("open_theft", "theft", "muted_alarm"):
        frames = _burst(
            at,
            counter,
            sources=["microphone", "vibration"],
            confidence=rng.randint(82, 96),
            duration_s=rng.randint(60, 600),
            energy=rng.randint(150, 240),
            battery_pct=battery,
        )
        if kind == "theft":
            closing = _Closing(
                at + timedelta(minutes=35),
                "theft",
                "ola",
                "przewoźnik zabrał 5 kłód ponad wydanie",
            )
            return frames, closing
        return frames, None
    # same wibracje, niska pewność = "możliwa manipulacja"
    frames = _burst(
        at,
        counter,
        sources=["vibration"],
        confidence=rng.randint(45, 60),
        duration_s=rng.randint(3, 15),
        energy=rng.randint(30, 90),
        battery_pct=battery,
    )
    return frames, _Closing(
        at + timedelta(minutes=50), "false_alarm", "blazej", "zwierzę przy stosie"
    )


async def demo_exists(session: AsyncSession) -> bool:
    return bool(
        await session.scalar(select(Sensor.id).where(Sensor.id.startswith(DEMO_PREFIX)))
    )


async def reset_demo(session: AsyncSession) -> None:
    """Usuwa czujniki demo z całą historią i konta demo. Leśnictwa i admin zostają."""
    demo = Sensor.id.startswith(DEMO_PREFIX)
    ids = select(Sensor.id).where(demo)
    for model in (Message, Alarm, Release):
        await session.execute(delete(model).where(model.sensor_id.in_(ids)))
    await session.execute(delete(Sensor).where(demo))
    logins = [login for login, *_ in DEMO_USERS]
    user_ids = select(User.id).where(User.login.in_(logins))
    await session.execute(
        delete(PushSubscription).where(PushSubscription.user_id.in_(user_ids))
    )
    await session.execute(delete(User).where(User.login.in_(logins)))
    await session.commit()


async def _ranges(session: AsyncSession) -> dict[str, int]:
    ranges = {r.name: r.id for r in await session.scalars(select(Range))}
    for name in (DABROWA, OLSZYNY):
        if name not in ranges:
            r = Range(name=name)
            session.add(r)
            await session.flush()
            ranges[name] = r.id
    return ranges


async def create_demo(
    session: AsyncSession, now: datetime | None = None, seed: int = 42
) -> dict:
    """Tworzy dane demo. Zakłada, że ich jeszcze nie ma (sprawdź `demo_exists`)."""
    now = now or datetime.now(UTC)
    rng = random.Random(seed)
    ranges = await _ranges(session)

    password_hash = await hash_password(settings.seed_demo_password)
    users = 0
    for login, full_name, role, range_name in DEMO_USERS:
        if await session.scalar(select(User.id).where(User.login == login)):
            log.info("Konto %s już istnieje, pomijam", login)
            continue
        session.add(
            User(
                login=login,
                full_name=full_name,
                role=role,
                password_hash=password_hash,
                range_id=ranges[range_name] if range_name else None,
                must_change_password=False,
            )
        )
        users += 1

    plans: dict[str, _Plan] = {}
    for s in DEMO_SENSORS:
        mounted = s.lat is not None
        session.add(
            Sensor(
                id=s.id,
                name=s.name,
                range_id=ranges[s.range_name],
                lat=s.lat,
                lon=s.lon,
                active=mounted and s.scenario != "off",
            )
        )
        plans[s.id] = _plan(s, now, rng)
    await session.flush()  # czujniki muszą być w bazie przed wydaniami (klucz obcy)
    for plan in plans.values():
        session.add_all(plan.releases)
    await session.commit()

    frames = 0
    for sensor_id, plan in plans.items():
        for frame in plan.frames:
            await ingest(
                session,
                sensor_id,
                frame.payload.hex(),
                frame.at,
                rng.randint(-120, -95),
            )
            frames += 1
        for closing in plan.closings:
            alarm = await session.scalar(
                select(Alarm)
                .where(Alarm.sensor_id == sensor_id, Alarm.status == "new")
                .order_by(Alarm.started_at)
                .limit(1)
            )
            alarm.status = closing.status
            alarm.response_by = closing.by
            alarm.response_at = closing.at
            alarm.response_comment = closing.comment
            sensor = next(s for s in DEMO_SENSORS if s.id == sensor_id)
            # pozycja z telefonu leśniczego: kilkanaście metrów od czujnika
            alarm.response_lat = sensor.lat + rng.uniform(-0.0002, 0.0002)
            alarm.response_lon = sensor.lon + rng.uniform(-0.0002, 0.0002)
        await session.commit()

    return {"users": users, "sensors": len(DEMO_SENSORS), "frames": frames}
