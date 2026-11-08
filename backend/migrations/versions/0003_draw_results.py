"""Allow drawn matches: best of 3 can end level after round 3, so results.winner is nullable."""
from alembic import op
import sqlalchemy as sa

revision = '0003_draw_results'
down_revision = '0002_history'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('results', 'winner', existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Drawn results cannot satisfy NOT NULL; remove them before restoring the constraint.
    op.execute('DELETE FROM results WHERE winner IS NULL')
    op.alter_column('results', 'winner', existing_type=sa.Integer(), nullable=False)
