"""Allow durable reindexing without mutating source analysis or existing profiles."""

from alembic import op

revision = "002"
down_revision = "001"


def upgrade():
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute("""ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN (
        'verify_upload', 'analyze_asset', 'build_project', 'apply_message', 'render_version',
        'reconcile_storage', 'delete_project', 'reindex_embeddings'))""")


def downgrade():
    raise RuntimeError("Restore a verified backup rather than discarding queued work")
