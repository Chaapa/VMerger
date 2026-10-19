from prometheus_client import CollectorRegistry, Gauge, generate_latest

from .db import connect


def exposition(owner_id):
    # Read shared durable state: values remain correct with multiple API/worker processes.
    registry = CollectorRegistry()
    count = Gauge(
        "vmerger_jobs", "Current jobs by bounded status and queue", ["queue", "status"], registry=registry
    )
    age = Gauge("vmerger_oldest_queued_seconds", "Age of oldest waiting job", ["queue"], registry=registry)
    failures = Gauge("vmerger_failed_calls", "Failed provider calls in the last hour", registry=registry)
    with connect() as conn:
        rows = conn.execute(
            """SELECT j.queue,j.status,count(*) n FROM jobs j JOIN projects p ON p.id=j.project_id
            WHERE p.owner_id=%s GROUP BY j.queue,j.status""",
            (owner_id,),
        ).fetchall()
        for queue in ("io", "ai", "render"):
            for status in ("queued", "running", "succeeded", "failed", "cancelled"):
                count.labels(queue, status).set(
                    next((r["n"] for r in rows if r["queue"] == queue and r["status"] == status), 0)
                )
            row = conn.execute(
                """SELECT coalesce(max(extract(epoch from now()-j.created_at)),0) age
                FROM jobs j JOIN projects p ON p.id=j.project_id
                WHERE j.status='queued' AND j.queue=%s AND p.owner_id=%s""",
                (queue, owner_id),
            ).fetchone()
            age.labels(queue).set(float(row["age"]))
        failures.set(
            conn.execute(
                """SELECT count(*) n FROM ai_calls a JOIN projects p ON p.id=a.project_id
            WHERE p.owner_id=%s AND a.status='failed' AND a.created_at>now()-interval '1 hour'""",
                (owner_id,),
            ).fetchone()["n"]
        )
    return generate_latest(registry)
