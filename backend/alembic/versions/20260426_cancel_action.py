"""添加取消勘误审计动作

Revision ID: 20260426_cancel_action
Revises: 20260426_errata_workbench
Create Date: 2026-04-26 16:30:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260426_cancel_action"
down_revision: Union[str, None] = "20260426_errata_workbench"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE errataauditaction ADD VALUE IF NOT EXISTS 'CANCEL'")


def downgrade() -> None:
    pass
