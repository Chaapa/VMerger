"""PostgreSQL lease queue: at-least-once execution, fenced publication."""

import threading
from contextlib import contextmanager
from uuid import uuid4

from .config import settings
from .db import connect, jsonb


class LeaseLost(RuntimeError):
    pass


def claim(queues=("io", "ai", "render")):
    with connect() as conn:
        conn.execute("""UPDATE jobs SET status=CASE WHEN cancel_requested THEN 'cancelled'
                         WHEN attempt>=max_attempts THEN 'failed' ELSE 'queued' END,
                         locked_by=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=now()
                         WHERE status='running' AND lease_expires_at<now()""")
        conn.execute("""UPDATE jobs SET status='cancelled',updated_at=now()
                        WHERE status='queued' AND cancel_requested""")
        return conn.execute(
            """WITH candidate AS (
            SELECT j.id FROM jobs j JOIN projects p ON p.id=j.project_id
            WHERE j.status='queued' AND j.queue=ANY(%s) AND j.available_at<=now()
              AND NOT j.cancel_requested AND j.attempt<j.max_attempts AND p.status='active'
            ORDER BY j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1)
            UPDATE jobs j SET status='running',attempt=attempt+1,lease_token=gen_random_uuid(),
              locked_by=%s,lease_expires_at=now()+make_interval(secs=>%s),updated_at=now()
            FROM candidate c WHERE j.id=c.id RETURNING j.*""",
            (list(queues), str(uuid4()), settings().lease_seconds),
        ).fetchone()


def heartbeat(job):
    with connect() as conn:
        result = conn.execute(
            """UPDATE jobs SET lease_expires_at=now()+make_interval(secs=>%s),
            updated_at=now() WHERE id=%s AND lease_token=%s AND status='running'
            AND NOT cancel_requested AND lease_expires_at>now() RETURNING id""",
            (settings().lease_seconds, job["id"], job["lease_token"]),
        ).fetchone()
        return result is not None


@contextmanager
def keep_alive(job):
    stop = threading.Event()
    lost = threading.Event()

    def beat():
        while not stop.wait(max(1, settings().lease_seconds / 3)):
            try:
                if not heartbeat(job):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield lost
    finally:
        stop.set()
        thread.join(timeout=6)


def fence(conn, job):
    project = conn.execute(
        "SELECT status FROM projects WHERE id=%s FOR UPDATE", (job["project_id"],)
    ).fetchone()
    row = conn.execute(
        """SELECT * FROM jobs WHERE id=%s AND lease_token=%s AND status='running'
        AND NOT cancel_requested AND lease_expires_at>now() FOR UPDATE""",
        (job["id"], job["lease_token"]),
    ).fetchone()
    if not project or project["status"] != "active" or not row:
        raise LeaseLost("Job no longer owns its publication lease")


def succeed(conn, job):
    conn.execute(
        """UPDATE jobs SET status='succeeded',progress=1,locked_by=NULL,lease_token=NULL,
        lease_expires_at=NULL,error=NULL,updated_at=now() WHERE id=%s AND lease_token=%s""",
        (job["id"], job["lease_token"]),
    )


def fail(job, error, retry=False):
    with connect() as conn:
        conn.execute(
            """UPDATE jobs SET status=CASE WHEN cancel_requested THEN 'cancelled'
            WHEN %s AND attempt<max_attempts THEN 'queued' ELSE 'failed' END,
            locked_by=NULL,lease_token=NULL,lease_expires_at=NULL,error=%s,
            available_at=now()+interval '10 seconds',updated_at=now()
            WHERE id=%s AND lease_token=%s""",
            (
                retry,
                jsonb({"type": type(error).__name__, "message": "Processing failed; inspect worker logs"}),
                job["id"],
                job["lease_token"],
            ),
        )


def observe(job, role, metric, value, numerator=None, denominator=None, source="rule", details=None):
    with connect() as conn:
        conn.execute(
            """INSERT INTO eval_results(project_id,job_id,attempt,role,metric,value,
            numerator,denominator,source,details) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(job_id,attempt,role,metric) DO UPDATE SET value=excluded.value,
            numerator=excluded.numerator,denominator=excluded.denominator,details=excluded.details""",
            (
                job["project_id"],
                job["id"],
                job["attempt"],
                role,
                metric,
                value,
                numerator,
                denominator,
                source,
                jsonb(details or {}),
            ),
        )
