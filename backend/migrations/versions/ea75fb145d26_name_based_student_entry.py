"""Allow student participation profiles without email addresses."""
from alembic import op
import sqlalchemy as sa

revision = "ea75fb145d26"
down_revision = "d964ea034c15"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("participant_profiles") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(320), nullable=True)


def downgrade():
    # Refuse downgrade while name-only profiles exist; never discard students.
    with op.batch_alter_table("participant_profiles") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(320), nullable=False)
