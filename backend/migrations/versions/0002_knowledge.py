"""Create the single-owner knowledge base."""
import sqlalchemy as sa
from alembic import op

revision = "0002_knowledge"
down_revision = "0001_enable_vector"
branch_labels = None
depends_on = None


def identity_columns():
    return [sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False)]


def link(column, table):
    return sa.Column(column, sa.Integer(), sa.ForeignKey(f"{table}.id", ondelete="SET NULL"))


def description():
    return sa.Column("description", sa.Text(), nullable=False, server_default="")


def upgrade():
    op.create_table("categories", *identity_columns())
    op.create_table("projects", *identity_columns(), description(), link("category_id", "categories"))
    op.create_table("goals", *identity_columns(), description(), link("category_id", "categories"),
                    sa.Column("target_date", sa.Date()))
    op.create_table("tasks", *identity_columns(), description(), link("category_id", "categories"),
                    link("project_id", "projects"), link("goal_id", "goals"),
                    sa.Column("due_date", sa.Date()),
                    sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
                    sa.Column("status", sa.String(16), nullable=False, server_default="todo"),
                    sa.CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="task_status"),
                    sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="task_priority"))
    op.create_table("notes", *identity_columns(), link("category_id", "categories"),
                    link("project_id", "projects"), sa.Column("body", sa.Text(), nullable=False))


def downgrade():
    for table in ("notes", "tasks", "goals", "projects", "categories"):
        op.drop_table(table)
