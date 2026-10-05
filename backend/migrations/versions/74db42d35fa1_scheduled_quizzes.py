"""Scheduled quizzes and student assignments."""
from alembic import op
import sqlalchemy as sa

revision = '74db42d35fa1'
down_revision = '63c921c4a810'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('scheduled_quizzes',
        sa.Column('id', sa.Uuid(), primary_key=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('presentation_id', sa.Uuid(), sa.ForeignKey('presentations.id'), nullable=False),
        sa.Column('owner_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(160), nullable=False), sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False), sa.Column('questions', sa.JSON(), nullable=False))
    op.create_table('quiz_assignments',
        sa.Column('id', sa.Uuid(), primary_key=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('quiz_id', sa.Uuid(), sa.ForeignKey('scheduled_quizzes.id'), nullable=False),
        sa.Column('email', sa.String(320), nullable=False), sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.Column('answers', sa.JSON()), sa.Column('score', sa.Integer()), sa.UniqueConstraint('quiz_id', 'email'))
    op.create_index('ix_quiz_assignments_email', 'quiz_assignments', ['email'])


def downgrade():
    op.drop_table('quiz_assignments')
    op.drop_table('scheduled_quizzes')
