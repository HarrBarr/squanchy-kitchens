"""auth: users, upload review lifecycle, audit log, voided readings

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lets SQLite batch mode name (and so drop) the unnamed UNIQUE(sha256) from 0001.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_created", "audit_log", ["created_at"])
    op.create_index("ix_audit_user_created", "audit_log", ["user_id", "created_at"])

    # uploads: from "sha256 unique" to "active_sha256 unique" (NULL once voided).
    if op.get_bind().dialect.name == "mysql":
        op.drop_index("sha256", table_name="uploads")  # MySQL names UNIQUE(sha256) "sha256"
        with op.batch_alter_table("uploads") as b:
            _add_upload_columns(b)
    else:
        with op.batch_alter_table("uploads", naming_convention=NAMING) as b:
            b.drop_constraint("uq_uploads_sha256", type_="unique")
            _add_upload_columns(b)

    op.create_index("ix_uploads_sha256", "uploads", ["sha256"])
    op.create_index("ix_uploads_status", "uploads", ["status"])
    # Existing rows: the old import status "imported" becomes review status "active".
    op.execute("UPDATE uploads SET status = 'active', active_sha256 = sha256")

    with op.batch_alter_table("readings") as b:
        b.add_column(
            sa.Column("is_voided", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def _add_upload_columns(b) -> None:  # noqa: ANN001
    b.add_column(sa.Column("branch_id", sa.Integer(), nullable=True))
    b.add_column(sa.Column("active_sha256", sa.String(length=64), nullable=True))
    b.add_column(sa.Column("uploaded_by", sa.Integer(), nullable=True))
    b.add_column(sa.Column("flagged_by", sa.Integer(), nullable=True))
    b.add_column(sa.Column("flag_reason", sa.String(length=1000), nullable=True))
    b.add_column(sa.Column("flagged_at", sa.DateTime(), nullable=True))
    b.add_column(sa.Column("voided_by", sa.Integer(), nullable=True))
    b.add_column(sa.Column("voided_at", sa.DateTime(), nullable=True))
    b.add_column(sa.Column("void_reason", sa.String(length=1000), nullable=True))
    b.create_unique_constraint("uq_uploads_active_sha256", ["active_sha256"])
    b.create_foreign_key("fk_uploads_branch", "branches", ["branch_id"], ["id"])
    b.create_foreign_key("fk_uploads_uploaded_by", "users", ["uploaded_by"], ["id"])
    b.create_foreign_key("fk_uploads_flagged_by", "users", ["flagged_by"], ["id"])
    b.create_foreign_key("fk_uploads_voided_by", "users", ["voided_by"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("readings") as b:
        b.drop_column("is_voided")
    op.drop_index("ix_uploads_status", table_name="uploads")
    op.drop_index("ix_uploads_sha256", table_name="uploads")
    with op.batch_alter_table("uploads") as b:
        for fk in (
            "fk_uploads_voided_by",
            "fk_uploads_flagged_by",
            "fk_uploads_uploaded_by",
            "fk_uploads_branch",
        ):
            b.drop_constraint(fk, type_="foreignkey")
        b.drop_constraint("uq_uploads_active_sha256", type_="unique")
        for col in (
            "void_reason",
            "voided_at",
            "voided_by",
            "flagged_at",
            "flag_reason",
            "flagged_by",
            "uploaded_by",
            "active_sha256",
            "branch_id",
        ):
            b.drop_column(col)
        b.create_unique_constraint("sha256", ["sha256"])
    op.execute("UPDATE uploads SET status = 'imported'")
    op.drop_table("audit_log")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
