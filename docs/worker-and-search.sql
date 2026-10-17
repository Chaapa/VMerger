-- Reference statements for schema.sql. Run after creating the schema.
-- PREPARE installs examples in the current connection; it does not start workers.
-- Production code uses parameterized SQL and explicit short transactions.

-- $1: accepted queues, $2: worker instance ID, $3: positive lease seconds.
-- Commit immediately after claiming. Do not keep this transaction open for work.
PREPARE claim_job(text[], text, integer) AS
WITH candidate AS (
    SELECT j.id
    FROM jobs j JOIN projects p ON p.id = j.project_id
    WHERE j.status = 'queued' AND j.queue = ANY($1)
      AND NOT j.cancel_requested AND j.attempt < j.max_attempts
      AND j.available_at <= clock_timestamp() AND $3 > 0
      AND (p.status = 'active' OR j.kind IN ('delete_project', 'reconcile_storage'))
    ORDER BY j.available_at, j.created_at, j.id
    LIMIT 1 FOR UPDATE OF j SKIP LOCKED
)
UPDATE jobs j
SET status = 'running', attempt = j.attempt + 1,
    locked_by = $2, lease_token = gen_random_uuid(),
    lease_expires_at = clock_timestamp() + make_interval(secs => $3),
    updated_at = clock_timestamp()
FROM candidate c WHERE j.id = c.id
RETURNING j.*;

-- Zero rows means lost/expired/cancelled lease: stop, never publish.
PREPARE heartbeat_job(uuid, uuid, integer) AS
UPDATE jobs
SET lease_expires_at = clock_timestamp() + make_interval(secs => $3),
    updated_at = clock_timestamp()
WHERE id = $1 AND lease_token = $2 AND status = 'running'
  AND NOT cancel_requested AND lease_expires_at > clock_timestamp() AND $3 > 0
RETURNING id;

-- Reaper example. Production backoff is configurable and includes jitter.
PREPARE reclaim_expired AS
UPDATE jobs
SET status = CASE WHEN cancel_requested THEN 'cancelled'
                  WHEN attempt >= max_attempts THEN 'failed' ELSE 'queued' END,
    locked_by = NULL, lease_token = NULL, lease_expires_at = NULL,
    available_at = clock_timestamp() + interval '30 seconds',
    updated_at = clock_timestamp()
WHERE status = 'running' AND lease_expires_at <= clock_timestamp()
RETURNING id, status;

PREPARE cancel_waiting AS
UPDATE jobs SET status = 'cancelled', updated_at = clock_timestamp()
WHERE status = 'queued' AND cancel_requested
RETURNING id;

-- Internal worker operation; lock active project first, then this job, then objects.
-- This lock and the result/next-job writes MUST share the same transaction.
-- A standalone successful check does not authorize a later transaction to publish.
PREPARE lock_job_for_publication(uuid, uuid) AS
SELECT id, project_id FROM jobs
WHERE id = $1 AND lease_token = $2 AND status = 'running'
  AND NOT cancel_requested AND lease_expires_at > clock_timestamp()
FOR UPDATE;

-- With story locked: create validated immutable version, perform CAS, enqueue render.
-- $1 story, $2 project, $3 expected current (nullable), $4 new version.
-- Zero rows means conflict; roll back/replan, do not silently overwrite.
PREPARE promote_version(uuid, uuid, uuid, uuid) AS
UPDATE stories SET current_version_id = $4, status = 'rendering', updated_at = now()
WHERE id = $1 AND project_id = $2 AND current_version_id IS NOT DISTINCT FROM $3
RETURNING id;

-- $1 project, $2 VERIFIED authenticated user, $3 profile, $4 query vector, $5 limit.
-- MATERIALIZED ensures exact ranking within the filtered project/profile candidate set.
PREPARE search_exact(uuid, uuid, text, vector, integer) AS
WITH candidates AS MATERIALIZED (
    SELECT e.segment_id, e.embedding, s.asset_id, s.start_us, s.end_us, s.description
    FROM segment_embeddings e
    JOIN projects p ON p.id = e.project_id
    JOIN segments s ON s.project_id = e.project_id AND s.id = e.segment_id
    WHERE e.project_id = $1 AND p.owner_id = $2 AND p.status = 'active'
      AND e.profile_key = $3
)
SELECT segment_id, asset_id, start_us, end_us, description,
       1 - (embedding <=> $4) AS similarity
FROM candidates ORDER BY embedding <=> $4, segment_id LIMIT $5;

-- ANN for the fixed initial profile; a new model gets a separate query/index profile.
-- In the transaction executing this statement set:
-- SET LOCAL hnsw.iterative_scan = 'strict_order';
-- Tune ef_search/max_scan_tuples using recall/latency measurements.
-- The planner may choose an exact plan for small datasets; do not force HNSW blindly.
PREPARE search_ann(uuid, uuid, vector, integer) AS
SELECT e.segment_id, s.asset_id, s.start_us, s.end_us, s.description,
       1 - (e.embedding <=> $3) AS similarity
FROM segment_embeddings e
JOIN projects p ON p.id = e.project_id
JOIN segments s ON s.project_id = e.project_id AND s.id = e.segment_id
WHERE e.project_id = $1 AND p.owner_id = $2 AND p.status = 'active'
  AND e.profile_key = 'gemini-embedding-001:text-v1:768'
ORDER BY e.embedding <=> $3 LIMIT $4;
