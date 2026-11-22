"""Add text documents, index state and source-owned embeddings."""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0003_rag"
down_revision = "0002_knowledge"
branch_labels = None
depends_on = None


def state_columns():
    return [
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("index_state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("profile", sa.String()),
        sa.Column("index_error", sa.String()),
    ]


def upgrade():
    for column in state_columns():
        op.add_column("notes", column)
    op.create_table("documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        *state_columns(),
    )
    op.create_table("chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE")),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.CheckConstraint("num_nonnulls(note_id, document_id) = 1", name="chunk_source"),
        sa.UniqueConstraint("note_id", "start"), sa.UniqueConstraint("document_id", "start"),
    )


def downgrade():
    op.drop_table("chunks")
    op.drop_table("documents")
    for column in state_columns():
        op.drop_column("notes", column.name)
