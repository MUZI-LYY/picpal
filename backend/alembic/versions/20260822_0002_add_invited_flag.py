"""add invited flag to anonymous sessions

Revision ID: 20260822_0002
Revises: 20260821_0001
Create Date: 2026-08-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260822_0002"
down_revision: Union[str, None] = "20260821_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "anonymous_sessions",
        sa.Column("invited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("anonymous_sessions", "invited")
