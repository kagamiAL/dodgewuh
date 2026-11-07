"""Initial rooms and members registration schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_registration"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create registration tables without depending on evolving application models."""
    # Create the room first without its host FK to break the circular table dependency.
    op.create_table("rooms",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("code", sa.String(6), nullable=False, unique=True),
        sa.Column("host_id", sa.Uuid(), nullable=False),
        sa.Column("runtime_id", sa.Uuid(), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_reason", sa.String(32)))
    op.create_index("ix_rooms_runtime_id", "rooms", ["runtime_id"])
    op.create_table("members",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("name", sa.String(24), nullable=False),
        sa.Column("device", sa.String(6), nullable=False),
        sa.Column("slot", sa.Integer()),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("room_id", "device", "slot", name="uq_member_slot"),
        sa.CheckConstraint("device IN ('phone', 'screen')", name="ck_member_device"),
        sa.CheckConstraint("slot IS NULL OR slot BETWEEN 0 AND 3", name="ck_member_slot"))
    op.create_index("ix_members_room_id", "members", ["room_id"])
    # Add the reverse link after both tables exist; defer it for atomic room+host inserts.
    op.create_foreign_key("fk_rooms_host", "rooms", "members", ["host_id"], ["id"], deferrable=True, initially="DEFERRED")


def downgrade():
    """Remove registration data; use only after an explicit destructive rollback decision."""
    # Break the circular FK before dropping either table.
    op.drop_constraint("fk_rooms_host", "rooms", type_="foreignkey")
    op.drop_table("members")
    op.drop_table("rooms")
