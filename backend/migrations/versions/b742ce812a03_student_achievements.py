"""Configurable global student achievement thresholds."""
from alembic import op
import sqlalchemy as sa

revision = 'b742ce812a03'
down_revision = 'a631a1f4ce02'
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table('achievement_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('gold', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('platinum', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('diamond', sa.Integer(), nullable=False, server_default='100'),
        sa.CheckConstraint('id = 1', name='achievement_singleton'),
        sa.CheckConstraint('gold >= 1 AND platinum > gold AND diamond > platinum', name='achievement_order'))
    op.bulk_insert(table, [{'id': 1, 'gold': 10, 'platinum': 50, 'diamond': 100}])


def downgrade():
    op.drop_table('achievement_settings')
