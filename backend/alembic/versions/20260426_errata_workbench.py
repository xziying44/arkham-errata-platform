"""添加勘误工作台模型

Revision ID: 20260426_errata_workbench
Revises: b8888de7362f
Create Date: 2026-04-26 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_errata_workbench"
down_revision: Union[str, None] = "b8888de7362f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'ERRATA'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'REVIEWER'")
        op.execute("COMMIT")
        op.execute("UPDATE users SET role = 'ERRATA' WHERE role = 'USER'")

    errata_package_status = sa.Enum("WAITING_PUBLISH", "PUBLISHING", "PUBLISHED", "UNLOCKED", name="erratapackagestatus")
    errata_draft_status = sa.Enum("ERRATA", "WAITING_PUBLISH", "ARCHIVED", name="erratadraftstatus")
    errata_audit_action = sa.Enum("CREATE", "SAVE", "REVIEW_SAVE", "PACKAGE", "UNLOCK", "PUBLISH", name="errataauditaction")

    op.create_table(
        "errata_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_no", sa.String(length=32), nullable=False),
        sa.Column("status", errata_package_status, nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.Column("unlocked_by", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["unlocked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_no"),
    )
    op.create_index(op.f("ix_errata_packages_package_no"), "errata_packages", ["package_no"], unique=True)
    op.create_index(op.f("ix_errata_packages_status"), "errata_packages", ["status"], unique=False)

    op.create_table(
        "errata_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("arkhamdb_id", sa.String(length=16), nullable=False),
        sa.Column("status", errata_draft_status, nullable=False),
        sa.Column("original_faces", sa.JSON(), nullable=False),
        sa.Column("modified_faces", sa.JSON(), nullable=False),
        sa.Column("changed_faces", sa.JSON(), nullable=False),
        sa.Column("rendered_previews", sa.JSON(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["errata_packages.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_errata_drafts_archived_at"), "errata_drafts", ["archived_at"], unique=False)
    op.create_index(op.f("ix_errata_drafts_arkhamdb_id"), "errata_drafts", ["arkhamdb_id"], unique=False)
    op.create_index(op.f("ix_errata_drafts_package_id"), "errata_drafts", ["package_id"], unique=False)
    op.create_index(op.f("ix_errata_drafts_status"), "errata_drafts", ["status"], unique=False)

    op.create_table(
        "errata_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("arkhamdb_id", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", errata_audit_action, nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("changed_faces", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["errata_drafts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_errata_audit_logs_action"), "errata_audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_errata_audit_logs_arkhamdb_id"), "errata_audit_logs", ["arkhamdb_id"], unique=False)
    op.create_index(op.f("ix_errata_audit_logs_draft_id"), "errata_audit_logs", ["draft_id"], unique=False)
    op.create_index(op.f("ix_errata_audit_logs_user_id"), "errata_audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_errata_audit_logs_user_id"), table_name="errata_audit_logs")
    op.drop_index(op.f("ix_errata_audit_logs_draft_id"), table_name="errata_audit_logs")
    op.drop_index(op.f("ix_errata_audit_logs_arkhamdb_id"), table_name="errata_audit_logs")
    op.drop_index(op.f("ix_errata_audit_logs_action"), table_name="errata_audit_logs")
    op.drop_table("errata_audit_logs")
    op.drop_index(op.f("ix_errata_drafts_status"), table_name="errata_drafts")
    op.drop_index(op.f("ix_errata_drafts_package_id"), table_name="errata_drafts")
    op.drop_index(op.f("ix_errata_drafts_arkhamdb_id"), table_name="errata_drafts")
    op.drop_index(op.f("ix_errata_drafts_archived_at"), table_name="errata_drafts")
    op.drop_table("errata_drafts")
    op.drop_index(op.f("ix_errata_packages_status"), table_name="errata_packages")
    op.drop_index(op.f("ix_errata_packages_package_no"), table_name="errata_packages")
    op.drop_table("errata_packages")
