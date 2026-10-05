"""Reusable participant profiles with separate session credentials."""
from alembic import op
import sqlalchemy as sa
revision = '85ab736bb021'
down_revision = '74db42d35fa1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('participant_profiles',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('name', sa.String(60), nullable=False),
        sa.Column('email', sa.String(320), nullable=False, unique=True),
        sa.Column('phone', sa.String(25), nullable=False))
    with op.batch_alter_table('participants') as batch:
        batch.add_column(sa.Column('profile_id', sa.Uuid(), nullable=True))
        batch.create_foreign_key('participant_profile_fk', 'participant_profiles', ['profile_id'], ['id'])
        batch.create_unique_constraint('session_participant_profile', ['session_id', 'profile_id'])


def downgrade():
    with op.batch_alter_table('participants') as batch:
        batch.drop_constraint('session_participant_profile', type_='unique')
        batch.drop_constraint('participant_profile_fk', type_='foreignkey')
        batch.drop_column('profile_id')
    op.drop_table('participant_profiles')
