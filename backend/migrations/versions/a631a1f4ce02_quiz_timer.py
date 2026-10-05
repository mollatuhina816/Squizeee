"""Persist quiz duration and each student's attempt deadline and draft."""
from alembic import op
import sqlalchemy as sa

revision = 'a631a1f4ce02'
down_revision = '85ab736bb021'
branch_labels = None
depends_on = None


def upgrade():
    for table in ['presentations', 'scheduled_quizzes']:
        op.add_column(table, sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('quiz_assignments', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('quiz_assignments', sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('quiz_assignments', sa.Column('draft_answers', sa.JSON(), nullable=True))
    op.create_index('ix_quiz_assignments_deadline_at', 'quiz_assignments', ['deadline_at'])


def downgrade():
    op.drop_index('ix_quiz_assignments_deadline_at', table_name='quiz_assignments')
    for column in ['draft_answers', 'deadline_at', 'started_at']:
        op.drop_column('quiz_assignments', column)
    for table in ['scheduled_quizzes', 'presentations']:
        op.drop_column(table, 'duration_minutes')
