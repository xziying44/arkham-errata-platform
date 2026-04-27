"""为用户增加备注字段

Revision ID: 20260427_user_note
Revises: 20260426_cancel_action
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260427_user_note"
down_revision = "20260426_cancel_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("note", sa.Text(), nullable=False, server_default=""))
    op.alter_column("users", "note", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "note")
