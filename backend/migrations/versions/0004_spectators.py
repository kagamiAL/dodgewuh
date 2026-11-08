"""Watch-only spectator members: a third device kind with no slot."""
from alembic import op
import sqlalchemy as sa

revision = '0004_spectators'
down_revision = '0003_draw_results'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('members', 'device', existing_type=sa.String(6), type_=sa.String(9), existing_nullable=False)
    op.drop_constraint('ck_member_device', 'members', type_='check')
    op.create_check_constraint('ck_member_device', 'members', "device IN ('phone', 'screen', 'spectator')")


def downgrade():
    op.execute("DELETE FROM members WHERE device = 'spectator'")
    op.drop_constraint('ck_member_device', 'members', type_='check')
    op.create_check_constraint('ck_member_device', 'members', "device IN ('phone', 'screen')")
    op.alter_column('members', 'device', existing_type=sa.String(9), type_=sa.String(6), existing_nullable=False)
