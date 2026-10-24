# Implemented scope and alpha limits

October 24, 2026. This describes shipped code rather than the full target architecture.

## Implemented

The React Stories interface includes chat, sources, playback, versions and charts. Sessions use HttpOnly cookies; mutations check Origin and an application request header. Project operations verify ownership. Browser clients receive no application or S3 secrets.

Media passes size, ffprobe, duration and resolution checks. Sources upload to SeaweedFS, then are read back and verified with SHA-256. ETag is not treated as a content hash. Duplicate sources within a project are reused. Application disk holds temporary working copies, removed afterward; persistent files inside SeaweedFS's data directory are its object-storage implementation.

Analysis creates scenes and normalized 768-dimensional text embeddings. Full-text search needs no model. Semantic search embeds the query and searches only one project/profile. Small projects use exact search. A partial HNSW index exists, but is not claimed as every query's execution path.

Director → music → editor → reviewer use structured responses. Deterministic validation checks UUIDs, source availability, intervals, duration and music rights. Effects are none/warm/monochrome/fade; model-supplied FFmpeg expressions are not executed. Reviewer judgment is not a substitute for validation or ground truth.

Compatible inference endpoints can run on owned or rented GPUs. Explicit creative-role backups handle network failures, timeouts and 429/5xx while auditing each attempt. Fallback is off by default. Automatic GPU rental, shared circuit breaking and monetary budgets are not implemented. See the [Vast.ai/self-hosting guide](self-hosted-llm.md).

The PostgreSQL queue supports concurrent workers, lease tokens, heartbeat, expiry recovery, attempt limits and cancellation. Publication checks the current lease and expected parent version. Object, plan, render and current-version changes commit after S3 verification and complete decode. Unverified objects are not served.

## Differences from the target design

| Area | Alpha | Target |
|---|---|---|
| Sign-in | One owner, random workspace key | OIDC, multiple owners, collaboration |
| SQL | psycopg with explicit SQL; Alembic uses SQLAlchemy | ORM where it simplifies domain code |
| Upload | API streaming, 500 MB cap, whole-file retry | Resumable direct multipart S3 |
| Updates | Snapshots every 2.5 seconds | SSE with snapshot recovery |
| Analysis | Gemini inline proxy ≤14 MB; compatible vision frame samples | Chunking, precise boundaries, provider-file lifecycle |
| Speech | Model phrases from native video; no speech in frame mode | faster-whisper and word alignment |
| Music | User-confirmed rights, imported S3 library | Licensed-catalog integrations |
| Agent loops | One role pass; reviewer rejection stops assembly | Bounded repair loops and monetary budgets |
| Effects | Four built-in presets | Versioned extensible catalog |
| Storage | Verification, unreferenced failed-object cleanup | Full reconciliation, retention and project deletion |
| Observability | Worker JSON events, DB metrics, charts, Prometheus/Grafana | OTel, Loki/Tempo, alert delivery |
| DB access | One alpha account | Separate least-privilege migration/API/worker roles |

upload_sessions, derivatives and provider_files were reserved in the baseline schema; this slice does not implement their entire lifecycle. That debt is explicit; no placeholder records are created to imply completeness.

## Actual application measurements

- `plan_valid`: passed plans / checked plans in an attempt. Multiple stories accumulate numerator and denominator.
- `source_bounds_pass`: checked valid analysis intervals / all analysis intervals.
- `provider_approval`: the model reviewer's approval rate, source `provider`; not human approval or reviewer recall.
- `decode_pass`: 1 after full decode of a published render. Failures remain in jobs; this alone is not end-to-end success rate.
- `duration_error_seconds`: absolute output-duration minus planned-range duration. UI charts use completed renders.
- Model-call time, input/output tokens, status and model. Charts/p95 include failed calls. Cost stays `null` without verified pricing.
- Job processing time, queue status counts, oldest-job age and provider failures in the last hour.

UI N counts observations/attempts, not independent projects for scientific comparison. Human metrics, reviewer precision/recall, music fit and confidence intervals are specified in [agent evaluation](agent-evaluation.md), but unmeasured. Repeated calls are not independent samples.

## Before broader operation

Run selected live providers on footage permitted for transmission, label a real-trip dataset and review quality manually. Then add resumable uploads/reconciliation, OIDC, runtime-role permissions and spending limits. Scaling workers does not remove the limits of one disk, S3 node or database; high availability requires separate deployment and measurements.
