"""Initial schema and measured evaluation observations."""

from pathlib import Path

from alembic import op

revision = "001"
down_revision = None


def upgrade():
    source = Path(__file__).resolve().parents[2] / "docs" / "schema.sql"
    sql = source.read_text(encoding="utf-8").replace("BEGIN;", "").replace("COMMIT;", "")
    op.get_bind().exec_driver_sql(sql)
    op.execute("""CREATE TABLE eval_results (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        attempt integer NOT NULL,
        role text NOT NULL,
        metric text NOT NULL,
        value double precision NOT NULL,
        numerator double precision,
        denominator double precision CHECK (denominator IS NULL OR denominator > 0),
        source text NOT NULL CHECK (source IN ('rule','provider','human')),
        details jsonb NOT NULL DEFAULT '{}',
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(job_id,attempt,role,metric)
    )""")
    op.execute("CREATE INDEX eval_project_time ON eval_results(project_id,created_at)")


def downgrade():
    raise RuntimeError("Destructive downgrade is intentionally unsupported; restore a verified backup.")
