"""pełny model danych i hypertable messages

Revision ID: 6fcd82393702
Revises:
Create Date: 2026-10-25 15:31:16.128153

Tabele tworzone ręcznie (nie autogenerate), bo autogenerate wymaga działającej bazy.
Stan docelowy zgodny z app/models.py. Wyjątek: messages ma klucz (id, received_at),
bo TimescaleDB wymaga kolumny czasu w każdym unikalnym indeksie.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "6fcd82393702"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "ranges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )

    op.create_table(
        "sensors",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("range_id", sa.Integer(), sa.ForeignKey("ranges.id"), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_counter", sa.Integer(), nullable=True),
    )
    op.create_index("ix_sensors_range_id", "sensors", ["range_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("range_id", sa.Integer(), sa.ForeignKey("ranges.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "role IN ('forester', 'district_manager', 'admin')", name="ck_users_role"
        ),
    )
    op.create_index("ix_users_range_id", "users", ["range_id"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fcm_token", sa.String(255), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_label", sa.String(100), nullable=True),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    op.create_table(
        "releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sensor_id", sa.String(32), sa.ForeignKey("sensors.id"), nullable=False
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("carrier", sa.String(100), nullable=True),
        sa.Column("log_count", sa.Integer(), nullable=True),
        sa.Column("comment", sa.String(500), nullable=True),
    )
    op.create_index("ix_releases_sensor_id", "releases", ["sensor_id"])

    op.create_table(
        "alarms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sensor_id", sa.String(32), sa.ForeignKey("sensors.id"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.Integer(), nullable=False),
        sa.Column("sources", JSONB(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("energy", sa.Integer(), nullable=False),
        sa.Column("repeats", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_by", sa.String(50), nullable=True),
        sa.Column("response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_comment", sa.String(500), nullable=True),
    )
    op.create_index("ix_alarms_sensor_id", "alarms", ["sensor_id"])

    # Klucz złożony: TimescaleDB wymaga kolumny czasu w PK/unikalnych indeksach.
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sensor_id", sa.String(32), sa.ForeignKey("sensors.id"), nullable=False
        ),
        sa.Column("msg_type", sa.String(16), nullable=False),
        sa.Column("counter", sa.Integer(), nullable=False),
        sa.Column("payload_hex", sa.String(128), nullable=False),
        sa.Column("decoded", JSONB(), nullable=False),
        sa.Column("rssi", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", "received_at"),
    )
    op.create_index("ix_messages_received_at", "messages", ["received_at"])
    op.create_index("ix_messages_sensor_id", "messages", ["sensor_id"])
    op.execute("SELECT create_hypertable('messages', 'received_at')")


def downgrade() -> None:
    # Hypertable i indeksy znikają razem z tabelą. Rozszerzenie timescaledb zostaje celowo.
    op.drop_table("messages")
    op.drop_table("alarms")
    op.drop_table("releases")
    op.drop_table("push_subscriptions")
    op.drop_table("users")
    op.drop_table("sensors")
    op.drop_table("ranges")
