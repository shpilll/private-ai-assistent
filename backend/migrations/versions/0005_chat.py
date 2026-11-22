"""Persistent conversations and idempotent chat turns."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_chat"
down_revision = "0004_pending_deletions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("conversations", sa.Column("id", sa.Uuid(), primary_key=True),
                    sa.Column("title", sa.String(120), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("chat_turns", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("request_id", sa.Uuid(), nullable=False), sa.Column("prompt", sa.Text(), nullable=False),
                    sa.Column("result", JSONB(), nullable=False), sa.UniqueConstraint("conversation_id", "request_id"))


def downgrade():
    op.drop_table("chat_turns")
    op.drop_table("conversations")
