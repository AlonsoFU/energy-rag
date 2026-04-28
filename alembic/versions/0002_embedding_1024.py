"""embedding 1024 dims

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("DROP INDEX IF EXISTS idx_fragmentos_embedding;")
    op.execute("ALTER TABLE fragmentos ALTER COLUMN embedding TYPE vector(1024);")
    op.execute("CREATE INDEX idx_fragmentos_embedding ON fragmentos USING hnsw (embedding vector_cosine_ops);")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_fragmentos_embedding;")
    op.execute("ALTER TABLE fragmentos ALTER COLUMN embedding TYPE vector(768);")
    op.execute("CREATE INDEX idx_fragmentos_embedding ON fragmentos USING hnsw (embedding vector_cosine_ops);")
