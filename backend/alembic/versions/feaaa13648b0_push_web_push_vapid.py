"""push: Web Push (VAPID) zamiast tokenu FCM

Revision ID: feaaa13648b0
Revises: 5f41cec4e950
Create Date: 2026-11-09 12:00:00.000000

Subskrypcja przeglądarki to endpoint + dwa klucze (PushSubscription.toJSON()).
Tabela nie była jeszcze używana (brak endpointów), więc stare wiersze usuwamy
zamiast przenosić: token FCM i tak nie da się zamienić na subskrypcję Web Push.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "feaaa13648b0"
down_revision: Union[str, Sequence[str], None] = "5f41cec4e950"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM push_subscriptions")
    op.drop_constraint(
        "push_subscriptions_fcm_token_key", "push_subscriptions", type_="unique"
    )
    op.drop_column("push_subscriptions", "fcm_token")
    op.add_column("push_subscriptions", sa.Column("endpoint", sa.Text(), nullable=False))
    op.add_column(
        "push_subscriptions", sa.Column("p256dh", sa.String(100), nullable=False)
    )
    op.add_column("push_subscriptions", sa.Column("auth", sa.String(50), nullable=False))
    op.create_unique_constraint(
        "push_subscriptions_endpoint_key", "push_subscriptions", ["endpoint"]
    )


def downgrade() -> None:
    op.execute("DELETE FROM push_subscriptions")
    op.drop_constraint(
        "push_subscriptions_endpoint_key", "push_subscriptions", type_="unique"
    )
    op.drop_column("push_subscriptions", "auth")
    op.drop_column("push_subscriptions", "p256dh")
    op.drop_column("push_subscriptions", "endpoint")
    op.add_column(
        "push_subscriptions",
        sa.Column("fcm_token", sa.String(255), nullable=False),
    )
    op.create_unique_constraint(
        "push_subscriptions_fcm_token_key", "push_subscriptions", ["fcm_token"]
    )
