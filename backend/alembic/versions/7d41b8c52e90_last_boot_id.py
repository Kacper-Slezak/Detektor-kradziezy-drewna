"""sensors.last_boot_id: ochrona przed powtórką BOOT

Revision ID: 7d41b8c52e90
Revises: a3c9e1f20b47
Create Date: 2026-11-23 18:00:00.000000

Ramka BOOT wersji 2 niesie boot_id (numer uruchomienia płytki). Backend zapamiętuje
największy przyjęty i odrzuca BOOT, którego numer nie jest większy. Kolumna jest pusta
dla czujników, które boot_id jeszcze nie wysyłają.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d41b8c52e90"
down_revision: Union[str, Sequence[str], None] = "a3c9e1f20b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sensors", sa.Column("last_boot_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("sensors", "last_boot_id")
