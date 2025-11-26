"""Add user_memories table with pgvector for intelligent memory (Task #42597)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202502110002"
down_revision = "fefc279c0f5b"  # depends on RLS policies
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure vector extension is available (should already exist from initial schema)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create user_memories table with pgvector support
    op.create_table(
        "user_memories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
<<<<<<< HEAD
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_text", sa.Text(), nullable=False),
        # Vector embedding for semantic search (384 dimensions for all-MiniLM-L6-v2)
        # Note: pgvector's vector type is created via raw SQL below
        sa.Column("embedding", sa.Text(), nullable=True),  # Will be altered to vector(384)
=======
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_text", sa.Text(), nullable=False),
        # Vector embedding for semantic search (384 dimensions for all-MiniLM-L6-v2)
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        sa.Column(
            "memory_type",
            sa.Text(),
            nullable=True,
            server_default="context",
        ),
        sa.Column(
            "importance",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "memory_type IN ('preference', 'fact', 'emotion', 'context')",
            name="ck_user_memories_memory_type",
        ),
    )

<<<<<<< HEAD
    # Alter embedding column to use pgvector's vector type (384 dimensions)
    op.execute("""
        ALTER TABLE user_memories
        ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384);
    """)

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    # Create indices for fast lookups
    op.create_index(
        "idx_user_memories_user_id",
        "user_memories",
        ["user_id"],
    )

    op.create_index(
        "idx_user_memories_session_id",
        "user_memories",
        ["session_id"],
    )

    op.create_index(
        "idx_user_memories_created_at",
        "user_memories",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"},
    )

    # Create vector index for cosine similarity search (IVFFlat)
    # Note: This requires pgvector extension and may need manual creation via SQL
    # if the database user doesn't have sufficient privileges
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_memories_embedding_ivfflat
        ON user_memories
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)

<<<<<<< HEAD
    # Create trigger for auto-updating updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_user_memories_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_user_memories_updated_at
            BEFORE UPDATE ON user_memories
            FOR EACH ROW
            EXECUTE FUNCTION update_user_memories_updated_at();
    """)

    # Enable Row Level Security (RLS)
    op.execute("ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;")

    # RLS Policies
    op.execute("""
        CREATE POLICY "Users can view own memories"
            ON user_memories FOR SELECT
            USING (true);
    """)

    op.execute("""
        CREATE POLICY "Service role can insert memories"
            ON user_memories FOR INSERT
            WITH CHECK (true);
    """)

    op.execute("""
        CREATE POLICY "Service role can update memories"
            ON user_memories FOR UPDATE
            USING (true);
    """)

    op.execute("""
        CREATE POLICY "Service role can delete memories"
            ON user_memories FOR DELETE
            USING (true);
    """)

    # Grant permissions
    op.execute("GRANT ALL ON user_memories TO authenticated;")
    op.execute("GRANT ALL ON user_memories TO service_role;")

    # Add comment for documentation
    op.execute("""
        COMMENT ON TABLE user_memories IS 'MemO: Intelligent semantic memory storage with pgvector (Task #42597)';
    """)
    op.execute("""
        COMMENT ON COLUMN user_memories.embedding IS 'Sentence embedding vector (384-dim from all-MiniLM-L6-v2)';
=======
    # Add foreign key to users table (references auth.users in Supabase)
    # Note: In Supabase, auth.users is managed separately, so we may need to handle this manually
    # For now, we'll add a comment indicating the relationship
    op.execute("""
        COMMENT ON COLUMN user_memories.user_id IS 'References auth.users(id) - managed by Supabase Auth';
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    """)


def downgrade() -> None:
<<<<<<< HEAD
    # Drop RLS policies
    op.execute('DROP POLICY IF EXISTS "Users can view own memories" ON user_memories;')
    op.execute('DROP POLICY IF EXISTS "Service role can insert memories" ON user_memories;')
    op.execute('DROP POLICY IF EXISTS "Service role can update memories" ON user_memories;')
    op.execute('DROP POLICY IF EXISTS "Service role can delete memories" ON user_memories;')

    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trigger_user_memories_updated_at ON user_memories;")
    op.execute("DROP FUNCTION IF EXISTS update_user_memories_updated_at();")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_user_memories_embedding_ivfflat;")
    op.drop_index("idx_user_memories_created_at", table_name="user_memories")
    op.drop_index("idx_user_memories_session_id", table_name="user_memories")
    op.drop_index("idx_user_memories_user_id", table_name="user_memories")

    # Drop table
=======
    op.drop_index("idx_user_memories_embedding_ivfflat", table_name="user_memories")
    op.drop_index("idx_user_memories_created_at", table_name="user_memories")
    op.drop_index("idx_user_memories_session_id", table_name="user_memories")
    op.drop_index("idx_user_memories_user_id", table_name="user_memories")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    op.drop_table("user_memories")
