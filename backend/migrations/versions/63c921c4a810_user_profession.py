"""Persist teacher/student registration choice; existing users remain teachers."""
from alembic import op
import sqlalchemy as sa

revision = "63c921c4a810"
down_revision = "4b02c14516f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("profession", sa.String(20), nullable=False, server_default="teacher"))
    with op.batch_alter_table("users") as batch:
        batch.create_check_constraint("user_profession", "profession IN ('teacher','student')")


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("user_profession", type_="check")
        batch.drop_column("profession")
