"""为用户增加备注字段

Revision ID: 20260427_user_note
Revises: 20260426_publish_sessions
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260427_user_note"
down_revision = "20260426_publish_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "note" not in columns:
        op.add_column("users", sa.Column("note", sa.Text(), nullable=False, server_default=""))
    op.alter_column("users", "note", server_default=None)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "note" in columns:
        op.drop_column("users", "note")
