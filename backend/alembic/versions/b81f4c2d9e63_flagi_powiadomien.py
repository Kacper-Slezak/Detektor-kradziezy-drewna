"""flagi powiadomień: słaba bateria, brak kontaktu, koniec wydania

Revision ID: b81f4c2d9e63
Revises: a3c9e1f20b47
Create Date: 2026-11-24 12:00:00.000000

Push o słabej baterii, braku kontaktu i końcu wydania ma pójść raz, a nie przy każdej
ramce albo co kilka minut (services/push.py). Flaga mówi, że ten push jest już obsłużony.
Istniejące wiersze dostają false; stare, dawno zakończone wydania i tak nie dadzą pusha,
bo pętla odhacza bez wysyłki wszystko, co skończyło się ponad godzinę temu.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b81f4c2d9e63"
down_revision: Union[str, Sequence[str], None] = "a3c9e1f20b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table, column in (
        ("sensors", "low_battery_notified"),
        ("sensors", "silent_notified"),
        ("releases", "end_notified"),
    ):
        op.add_column(
            table,
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # wartość domyślna tylko dla istniejących wierszy; nowe ustawia aplikacja (jak `active`)
        op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    op.drop_column("releases", "end_notified")
    op.drop_column("sensors", "silent_notified")
    op.drop_column("sensors", "low_battery_notified")
