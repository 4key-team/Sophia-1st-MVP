"""Add mem0_opt_in column to users table (Task #42597)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "202502110003"
down_revision = "202502110002"  # depends on user_memories creation
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add mem0_opt_in column to users table
    op.add_column(
        "users",
        sa.Column(
            "mem0_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="User consent for Mem0 intelligent memory system"
        ),
    )

    # Create index for faster filtering by opt-in status
    op.create_index(
        "idx_users_mem0_opt_in",
        "users",
        ["mem0_opt_in"],
    )


def downgrade() -> None:
    op.drop_index("idx_users_mem0_opt_in", table_name="users")
    op.drop_column("users", "mem0_opt_in")
