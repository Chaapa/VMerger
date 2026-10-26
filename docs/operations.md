# Operations and measurements

## Health and monitoring

- `/livez` reports that the API process is running.
- `/readyz` checks database and S3 access.
- `/api/metrics` exposes authenticated Prometheus metrics.

Start the optional monitoring services:

```sh
docker compose --profile monitoring up -d prometheus grafana
```

Grafana is at `http://127.0.0.1:3000` with user `admin` and the generated `APP_TOKEN` as its initial password. Prometheus is at `http://127.0.0.1:9090`. Both bind to loopback. Grafana provisions the **VMerger · Operations** dashboard.

[`monitoring.py`](../vmerger/monitoring.py) reads durable database state on each scrape:

| Metric | Meaning |
|---|---|
| `vmerger_jobs` | Job count by queue and current status |
| `vmerger_oldest_queued_seconds` | Age since creation of the oldest queued job, by queue |
| `vmerger_failed_calls` | Failed provider attempts in the last hour |

[`deploy/alerts.yml`](../deploy/alerts.yml) covers API unavailability, old queued work and provider failures. Outbound alert delivery is not configured. Readiness does not probe AI providers; the AI team view shows configuration and credential availability.

## Application observations

Each observation is keyed by job, attempt, role and metric. Retries are separate attempts. The UI aggregates ratio metrics using their numerators and denominators; its N is the number of observation rows.

| Observation | Interpretation |
|---|---|
| `plan_valid` | Plans passing deterministic checks / plans checked in an attempt |
| `source_bounds_pass` | Valid intervals recorded after successful analysis; failed analyses do not add a zero observation |
| `provider_approval` | Model-review approvals / reviewed stories; this is a model judgment |
| `decode_pass` | Successful full decode recorded after a render is published; failed renders remain visible as failed jobs |
| `duration_error_seconds` | Absolute difference between rendered duration and the sum of planned clip ranges |

`decode_pass` and `source_bounds_pass` therefore describe successful recorded work, not end-to-end success rates. Human satisfaction and reviewer accuracy need separate evaluation.

Provider call history records the actual provider/model, purpose, status, latency and reported tokens. Failed primary attempts remain visible when a backup succeeds. Call counts and latency include attempts, so they do not equal user-job counts. Cost stays unknown without pricing data.

## Failure recovery

Workers heartbeat their leases. Expired jobs return to the queue unless cancelled or out of attempts. A stale lease cannot publish; a stale parent version cannot replace the current story. Inspect job status and worker logs before retrying work. Configuration, validation and reviewer failures need a corrected input or configuration.

The cleanup command removes failed storage objects only when no asset, render or derivative references them:

```sh
docker compose run --rm api python -m vmerger.cleanup
```

Objects stuck in `writing` after a process crash require investigation. Full reconciliation and project retention/deletion are not implemented.

See [deployment](deployment.md) for worker scaling, HTTPS and consistent backups. Restore time, availability targets and sustained throughput need measurements on the actual deployment.
