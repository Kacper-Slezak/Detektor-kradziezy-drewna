"""Model danych: leśnictwa, użytkownicy, czujniki, ramki, alarmy, wydania, push.

Tabela `messages` w bazie jest hypertable TimescaleDB (tworzy ją migracja Alembic).
Migracja zmienia jej klucz główny na (id, received_at), bo TimescaleDB wymaga
kolumny czasu w każdym unikalnym indeksie.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# JSONB w Postgresie, zwykły JSON w SQLite (testy)
JsonType = JSON().with_variant(JSONB(), "postgresql")
BigIntId = BigInteger().with_variant(Integer(), "sqlite")

ROLES = ("forester", "district_manager", "admin")


class Range(Base):
    """Leśnictwo. Leśniczy i czujniki są przypisane do jednego."""

    __tablename__ = "ranges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # forester / district_manager / admin
    range_id: Mapped[int | None] = mapped_column(ForeignKey("ranges.id"), index=True)
    active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False)


class PushSubscription(Base):
    """Token FCM urządzenia użytkownika do powiadomień o alarmach."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    fcm_token: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_label: Mapped[str | None] = mapped_column(String(100))


class Sensor(Base):
    """Czujnik = jedno miejsce składowania drewna."""

    __tablename__ = "sensors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # ID z sieci (DevEUI)
    name: Mapped[str | None] = mapped_column(String(100))  # nadaje leśniczy
    range_id: Mapped[int | None] = mapped_column(ForeignKey("ranges.id"), index=True)
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
    status: Mapped[str] = mapped_column(
        String(16), default="new"
    )  # new / theft / false
    response_by: Mapped[str | None] = mapped_column(String(50))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_comment: Mapped[str | None] = mapped_column(String(500))
