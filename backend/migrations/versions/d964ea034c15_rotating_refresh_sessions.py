"""Persistent refresh-token families and replay detection."""
from alembic import op
import sqlalchemy as sa

revision = "d964ea034c15"
down_revision = "c853df923b04"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("auth_sessions", sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False))
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])


def downgrade():
    op.drop_table("refresh_tokens")
    op.drop_column("auth_sessions", "remember_me")
