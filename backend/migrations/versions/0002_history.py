"""Add coordinator-owned allocation, assignment and match history."""
from alembic import op
import sqlalchemy as sa

revision = '0002_history'
down_revision = '0001_registration'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('worker_allocations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('room_id', sa.Uuid(), sa.ForeignKey('rooms.id'), nullable=False, unique=True),
        sa.Column('worker_url', sa.String(512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
        sa.Column('reason', sa.String(32)),
        sa.Column('report_seq', sa.Integer(), nullable=False))
    op.create_table('assignments',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('allocation_id', sa.Uuid(), sa.ForeignKey('worker_allocations.id'), nullable=False),
        sa.Column('member_id', sa.Uuid(), sa.ForeignKey('members.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('team', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(4), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('allocation_id', 'version', 'member_id'))
    op.create_table('matches',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('allocation_id', sa.Uuid(), sa.ForeignKey('worker_allocations.id'), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(32)),
        sa.UniqueConstraint('allocation_id', 'ordinal'))
    op.create_table('results',
        sa.Column('match_id', sa.Uuid(), sa.ForeignKey('matches.id'), primary_key=True),
        sa.Column('winner', sa.Integer(), nullable=False),
        sa.Column('team1', sa.Integer(), nullable=False),
        sa.Column('team2', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ('results', 'matches', 'assignments', 'worker_allocations'):
        op.drop_table(table)
