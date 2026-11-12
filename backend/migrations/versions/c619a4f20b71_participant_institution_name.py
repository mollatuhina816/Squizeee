"""Store institute name with each live-quiz participant."""
from alembic import op
import sqlalchemy as sa

revision = "c619a4f20b71"
down_revision = "9d47e02c61ab"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("participants", sa.Column("institution_name", sa.String(200), nullable=True))


def downgrade():
    op.drop_column("participants", "institution_name")
