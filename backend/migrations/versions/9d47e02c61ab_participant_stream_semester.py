"""Store stream and semester on each live-quiz participant."""
from alembic import op
import sqlalchemy as sa

revision = "9d47e02c61ab"
down_revision = "fb86ac256e37"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("participants", sa.Column("stream", sa.String(120), nullable=True))
    op.add_column("participants", sa.Column("semester", sa.String(60), nullable=True))


def downgrade():
    op.drop_column("participants", "semester")
    op.drop_column("participants", "stream")
