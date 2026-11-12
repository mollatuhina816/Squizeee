"""Persist pacing and participation settings with a presentation."""
from alembic import op
import sqlalchemy as sa

revision = "fb86ac256e37"
down_revision = "ea75fb145d26"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("presentations", sa.Column("live_settings", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("presentations", "live_settings")
