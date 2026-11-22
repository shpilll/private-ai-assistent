"""Store one-time deletion confirmations for the local agent."""
import sqlalchemy as sa
from alembic import op

revision = "0004_pending_deletions"
down_revision = "0003_rag"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("pending_deletions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("pending_deletions")
