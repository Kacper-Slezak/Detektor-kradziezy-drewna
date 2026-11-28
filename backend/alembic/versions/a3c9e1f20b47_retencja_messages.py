"""retencja messages: surowe ramki starsze niż 90 dni są usuwane

Revision ID: a3c9e1f20b47
Revises: feaaa13648b0
Create Date: 2026-11-09 19:00:00.000000

Bez tego hypertable `messages` rośnie bez końca (serwer ma 10 GB dysku).
TimescaleDB usuwa całe chunki (po 7 dni) starsze niż 90 dni, zadaniem w tle raz dziennie.
Alarmy, wydania i stan czujników (last_seen, bateria) są w osobnych tabelach i zostają.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3c9e1f20b47"
down_revision: Union[str, Sequence[str], None] = "feaaa13648b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT add_retention_policy('messages', INTERVAL '90 days', if_not_exists => true)")


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('messages', if_exists => true)")
