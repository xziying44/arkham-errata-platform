"""添加发布会话和目录预设

Revision ID: 20260426_publish_sessions
Revises: 20260426_cancel_action
Create Date: 2026-04-26 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260426_publish_sessions"
down_revision: Union[str, None] = "20260426_cancel_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


publishsessionstatus = postgresql.ENUM("DRAFT", "GENERATING", "SHEETS_READY", "URLS_READY", "PATCH_READY", "COMPLETED", "SUPERSEDED", "FAILED", name="publishsessionstatus", create_type=False)
publishartifactkind = postgresql.ENUM("CARD_IMAGE", "SHEET_FRONT", "SHEET_BACK", "TTS_BAG", "URL_MAPPING", "PATCH_ZIP", "MANIFEST", "REPORT", name="publishartifactkind", create_type=False)
publishartifactstatus = postgresql.ENUM("ACTIVE", "CONFIRMED", "SUPERSEDED", "DELETED", "FAILED", name="publishartifactstatus", create_type=False)
publishdirectorytargetarea = postgresql.ENUM("CAMPAIGNS", "PLAYER_CARDS", name="publishdirectorytargetarea", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        publishsessionstatus.create(bind, checkfirst=True)
        publishartifactkind.create(bind, checkfirst=True)
        publishartifactstatus.create(bind, checkfirst=True)
        publishdirectorytargetarea.create(bind, checkfirst=True)

    op.create_table(
        "publish_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("status", publishsessionstatus, nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=False),
        sa.Column("artifact_root", sa.String(length=512), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cleanup_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["errata_packages.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_publish_sessions_package_id"), "publish_sessions", ["package_id"], unique=False)
    op.create_index(op.f("ix_publish_sessions_status"), "publish_sessions", ["status"], unique=False)
    op.create_index(op.f("ix_publish_sessions_cleanup_at"), "publish_sessions", ["cleanup_at"], unique=False)

    op.create_table(
        "publish_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("kind", publishartifactkind, nullable=False),
        sa.Column("status", publishartifactstatus, nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["publish_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_publish_artifacts_session_id"), "publish_artifacts", ["session_id"], unique=False)
    op.create_index(op.f("ix_publish_artifacts_kind"), "publish_artifacts", ["kind"], unique=False)
    op.create_index(op.f("ix_publish_artifacts_status"), "publish_artifacts", ["status"], unique=False)

    op.create_table(
        "publish_directory_presets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("local_dir_prefix", sa.String(length=256), nullable=False),
        sa.Column("target_area", publishdirectorytargetarea, nullable=False),
        sa.Column("target_bag_path", sa.String(length=512), nullable=False),
        sa.Column("target_bag_guid", sa.String(length=16), nullable=False),
        sa.Column("target_object_dir", sa.String(length=256), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("local_dir_prefix"),
    )
    op.create_index(op.f("ix_publish_directory_presets_local_dir_prefix"), "publish_directory_presets", ["local_dir_prefix"], unique=False)
    op.create_index(op.f("ix_publish_directory_presets_target_area"), "publish_directory_presets", ["target_area"], unique=False)
    op.create_index(op.f("ix_publish_directory_presets_is_active"), "publish_directory_presets", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_publish_directory_presets_is_active"), table_name="publish_directory_presets")
    op.drop_index(op.f("ix_publish_directory_presets_target_area"), table_name="publish_directory_presets")
    op.drop_index(op.f("ix_publish_directory_presets_local_dir_prefix"), table_name="publish_directory_presets")
    op.drop_table("publish_directory_presets")
    op.drop_index(op.f("ix_publish_artifacts_status"), table_name="publish_artifacts")
    op.drop_index(op.f("ix_publish_artifacts_kind"), table_name="publish_artifacts")
    op.drop_index(op.f("ix_publish_artifacts_session_id"), table_name="publish_artifacts")
    op.drop_table("publish_artifacts")
    op.drop_index(op.f("ix_publish_sessions_cleanup_at"), table_name="publish_sessions")
    op.drop_index(op.f("ix_publish_sessions_status"), table_name="publish_sessions")
    op.drop_index(op.f("ix_publish_sessions_package_id"), table_name="publish_sessions")
    op.drop_table("publish_sessions")
