"""Minimalny model danych potrzebny do /ingest.

Pełny model (użytkownicy, leśnictwa, push...) i migracje Alembic -> osobne issue.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# JSONB w Postgresie, zwykły JSON w SQLite (testy)
JsonType = JSON().with_variant(JSONB(), "postgresql")
BigIntId = BigInteger().with_variant(Integer(), "sqlite")


class Sensor(Base):
    """Czujnik = jedno miejsce składowania drewna."""

    __tablename__ = "sensors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # ID z sieci (DevEUI)
    name: Mapped[str | None] = mapped_column(String(100))  # nadaje leśniczy
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    active: Mapped[bool] = mapped_column(default=True)
    battery_pct: Mapped[int | None]
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_counter: Mapped[int | None]


class Release(Base):
    """Wydanie drewna = wyciszenie czujnika na czas wywozu."""

    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    carrier: Mapped[str | None] = mapped_column(String(100))
    log_count: Mapped[int | None]
    comment: Mapped[str | None] = mapped_column(String(500))


class Message(Base):
    """Każda odebrana ramka. Docelowo hypertable TimescaleDB (w migracji)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True, autoincrement=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.id"), index=True)
    msg_type: Mapped[str] = mapped_column(String(16))
    counter: Mapped[int]
    payload_hex: Mapped[str] = mapped_column(String(128))
    decoded: Mapped[dict] = mapped_column(JsonType)
    rssi: Mapped[int | None]


class Alarm(Base):
    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_frame_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[int]
    sources: Mapped[list] = mapped_column(JsonType)
    confidence: Mapped[int]
    duration_s: Mapped[int]
    energy: Mapped[int]
    repeats: Mapped[int] = mapped_column(default=1)  # ile ramek złożyło się na alarm
    status: Mapped[str] = mapped_column(String(16), default="new")  # new / theft / false
    response_by: Mapped[str | None] = mapped_column(String(50))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_comment: Mapped[str | None] = mapped_column(String(500))
