"""Protected schema: stable synthetic IDs and encrypted field envelopes."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("members", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
                    sa.Column("nama", sa.Text(), nullable=False), sa.Column("ruangan", sa.Text()),
                    sa.Column("ktp_index", sa.String(64)), sa.Column("protected_fields", sa.JSON(), nullable=False),
                    sa.Column("revision", sa.Integer(), nullable=False))
    op.create_index("ix_members_ktp_index", "members", ["ktp_index"])
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("username", sa.String(64), unique=True, nullable=False),
                    sa.Column("password_hash", sa.Text(), nullable=False), sa.Column("role", sa.String(32), nullable=False),
                    sa.Column("permissions", sa.JSON(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False))
    op.create_table("assignments", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False),
                    sa.UniqueConstraint("user_id", "member_id"))
    op.create_index("ix_assignments_user_id", "assignments", ["user_id"])
    op.create_index("ix_assignments_member_id", "assignments", ["member_id"])
    op.create_table("sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("csrf_hash", sa.String(64), nullable=False),
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table("audit_events", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("actor_id", sa.Integer()), sa.Column("event_type", sa.String(64), nullable=False),
                    sa.Column("resource_id", sa.Integer()), sa.Column("result", sa.String(16), nullable=False),
                    sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("correlation_id", sa.String(36), nullable=False),
                    sa.Column("fields", sa.JSON(), nullable=False))
    op.create_table("import_runs", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("source_sha256", sa.String(64), unique=True, nullable=False),
                    sa.Column("record_count", sa.Integer(), nullable=False), sa.Column("column_count", sa.Integer(), nullable=False),
                    sa.Column("created_at", sa.DateTime(), nullable=False))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled. Restore into an isolated new database; see docs/OPERATIONS.md")
