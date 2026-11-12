"""Live engagement settings, moderation and unique audience votes."""
from alembic import op
import sqlalchemy as sa

revision = 'c853df923b04'
down_revision = 'b742ce812a03'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('live_sessions', sa.Column('live_settings', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('live_sessions', sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('live_sessions', sa.Column('revealed', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('participants', sa.Column('team', sa.Integer(), nullable=True))
    op.create_table('audience_questions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('session_id', sa.Uuid(), sa.ForeignKey('live_sessions.id'), nullable=False),
        sa.Column('participant_id', sa.Uuid(), sa.ForeignKey('participants.id'), nullable=False),
        sa.Column('text', sa.String(500), nullable=False),
        sa.Column('status', sa.String(20), nullable=False))
    op.create_index('ix_audience_questions_session_id', 'audience_questions', ['session_id'])
    op.create_table('audience_votes',
        sa.Column('question_id', sa.Uuid(), sa.ForeignKey('audience_questions.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('participant_id', sa.Uuid(), sa.ForeignKey('participants.id'), primary_key=True))


def downgrade():
    op.drop_table('audience_votes')
    op.drop_table('audience_questions')
    op.drop_column('participants', 'team')
    op.drop_column('live_sessions', 'revealed')
    op.drop_column('live_sessions', 'paused_at')
    op.drop_column('live_sessions', 'live_settings')
