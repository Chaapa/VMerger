# VMerger: validation, monitoring and testing

Date: October 23, 2026. Status: target implementation and release requirements. The alpha implements part of this design; see [implemented scope](implementation.md) and [measured validation](local-validation.md). Related documents: [architecture](architecture.md), [agents](agents-and-effects.md), [early SQL checks](validation.md).

## 1. What quality means

The system must accept supported material, retain it, produce a technically valid film matching the request, and explain recoverable failures. Quality has three layers:

1. Deterministic checks of files, access, plans, versions and output.
2. Reliability checks for API, queues, storage, rendering and providers.
3. Content evaluation: instruction compliance, storytelling, music fit and editing choices.

Every new stage receives validators, metrics, error handling and tests alongside implementation. Agent promises and successful API responses do not establish a finished result. Ready status requires a verified file.

## 2. Boundary validation

| Boundary | Check | Failure behavior |
|---|---|---|
| HTTP / chat | Verified identity, ownership, request schema/size, request ID and fingerprint | Explain failure without exposing another project's data or causing side effects |
| Upload | S3 ListParts, actual size/SHA-256, ffprobe container/codecs, duration/resolution/resource limits | Prevent analysis; mark corrupt import failed |
| Decode | Streams, orientation, timestamps, VFR, HDR/color profile | Normalize supported input or explicitly identify unsupported format |
| Analysis / vectors | Response schema, source bounds, allowed IDs, finite values, profile/dimension/normalization | Do not publish into catalog; bounded retry or stage failure |
| Agent tool | Allowed operation, argument schema, access, base version, time/step/cost limits | Reject and account for the attempt; retain valid context |
| Film plan | Real clips/resources, ranges, transitions, speed, music, effects, parameters and user constraints | Block rendering and return specific findings to orchestration |
| Version / file publication | Active project, current lease/base version, verified object and matching report | Reject stale publication and preserve current data |
| Preview / export | Metadata, full decode, expected tracks/duration, time map, S3 size/availability | No ready status; retry or create a corrected version |
| Deletion / cleanup | Active uploads/leases, retained-version references, temporary URL expiry and backups | Delete only after dependencies clear; retry incomplete cleanup |

Distinguish blocking errors from warnings. Black frames, silence and hard cuts may be intentional; detectors provide context-aware signals. Unknown sources, out-of-bounds ranges, lost required scenes and cross-project access are blocking errors.

Decode untrusted media in an unprivileged process with CPU, memory, time and scratch limits. Treat transcripts, effect catalogs and metadata as data. Never execute model arguments as shell commands or arbitrary FFmpeg expressions.

### Edit-plan checks

Resolve references against actual project resources and verify:

- Half-open ranges, speed/overlap-adjusted duration, and source/occurrence/output time coordinates.
- Required/excluded moments, order, duration pins and “keep the edit” constraints.
- Effect version/resource compatibility with the engine, including fonts, LUTs and overlays.
- Music/speech placement, loudness bounds and word-safe boundaries where timestamps permit.
- Required provenance and usage confirmation for imported resources.
- Reproduction from the saved plan without another model request.

ASR can be wrong. Transcript-based boundary checks do not guarantee natural phrase endings; inspect audio and evaluate quality too.

### Output-file checks

Run ffprobe and a full decode after rendering. Verify container, expected tracks, geometry, frame rate, duration and timestamps. Tolerances belong to the render profile and account for frames, audio samples and codec delay rather than one universal threshold.

Sync fixtures use known audio impulses and visual markers. On real footage, timestamps detect technical offset but do not establish correct lip sync. Check loudness/clipping against the audio profile, accounting for expected pauses/fades.

Render fingerprints include plan version, resource hashes, profile and engine build. Changed effects, resources or validators require new verification. Replacing a failed effect creates a new version; committed versions are immutable.

### Validation report

The common report has stage, validator version, target ID, input fingerprint, optional output SHA-256, status (`passed`, `warnings`, `failed`), findings with code/severity/location, timestamp and duration.

Initially store compact reports in job checkpoints and result metadata; detailed reports can use S3. Final report/status publication is atomic and lease-checked. Publication matches fingerprint/hash to the exact object. Multiple output formats use render ID/fingerprint so reports cannot overwrite one another.

Job-history cleanup preserves reports needed by live versions. If independent query/retention is required, add `validation_runs` with project/result references. SQL alone does not enforce these application rules.

## 3. Errors, retries and recovery

Stable codes include unsupported_media, invalid_plan, provider_rate_limit, storage_unavailable, render_failed, budget_exceeded and stale_version. Users get a clear explanation/current status; diagnostic logs retain correlation IDs.

- Retry transient network, storage and provider failures with bounded attempts, jittered delays and Retry-After support.
- Data/access errors do not retry forever. Plan repair is a creative attempt consuming the shared budget.
- During widespread dependency failure, limit new calls and probe recovery while retaining queued work.
- Reserve AI spend before a call and reconcile actual usage afterward. Unknown costs retain a conservative reservation until reconciled.
- Lease expiry, cancellation and project deletion prohibit publication. Late external responses cannot mutate project state.
- Resume from verified checkpoints and preserve previous ready versions. Distinguish a new in-progress version from the latest ready result.

These are target behaviors. The implemented creative-role fallback is explicitly configured and described in [providers](providers.md); it does not provide a shared circuit breaker or monetary budget controller.

## 4. Observability and deployment

| Component | Role | Introduction |
|---|---|---|
| Structured JSON logs | Events, errors, request/job correlation | First working stage |
| OpenTelemetry SDK | API → queue → worker → model/S3/render traces | Early integrations |
| Prometheus | Application, PostgreSQL, host and storage metrics | First server environment |
| Grafana | Health, performance and cost dashboards | First server environment |
| Alertmanager | Grouping, deduplication and routing | First continuously operated environment |
| Collector + Tempo | Receive/query distributed traces | Multiple worker hosts, or earlier for diagnosis |
| Loki | Central log search | Multiple hosts or inconvenient local search |

One server can start with size-bounded JSON logs, Prometheus, Grafana and Alertmanager, with traces inspected during development. Additional telemetry storage uses a deployment profile. Export is asynchronous and buffered with limits; monitoring failure must not stop editing, and dropped telemetry must be measured.

Prometheus stores metrics. Do not put raw logs/traces into application PostgreSQL tables, which retain business state, ai_calls and agent audit. Initial configurable retention targets: metrics 30 days, logs 14 days, traces 7 days, with separate disk limits. Telemetry must not fill the database/scratch disk. [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/).

### Correlation and access

Private logs/traces contain request/project/job IDs, attempt, optional story/version IDs, role, tool, error code and trace ID. Serialize trace context into jobs; each stage/retry gets a linked span rather than one hours-long project span. Record prompt version, model, parameters and input fingerprints without recording full prompts/transcripts/video by default.

Exclude API keys, cookies, tokens, signed URLs and media bodies. Sanitize provider errors. Debug-content capture is explicitly enabled for test data with limited retention. Business audit remains complete even when traces are sampled.

Metric labels exclude user/project/job IDs, filenames and arbitrary text. Bound them to queue, stage, role, configured model alias, error code and route template. [Prometheus instrumentation guidance](https://prometheus.io/docs/practices/instrumentation/).

| Area | Measurements |
|---|---|
| API | Request/5xx counts, route p50/p95/p99, active requests/SSE, DB connection wait |
| Queues | Pending/active counts, oldest runnable age, wait, retries, expired leases, cancellations |
| Workers | Heartbeat, slot use, stage progress, last progress, restarts, stale-publication rejection |
| AI / agents | Latency, 429/5xx/timeouts, schema failures, steps/repairs, budget limits, tokens/cost |
| Rendering | Preparation/render/validation time, render seconds per output second, decode errors, CPU/GPU |
| PostgreSQL / search | Connections, locks, long transactions, size, query latency, evaluated recall |
| NAS / S3 | Read/write errors/latency, free space, incomplete multipart, orphans, throughput |
| User outcome | Time to first valid preview, final job success, export, edits and version returns |
| Maintenance | Backup/restore age, S3/DB reconciliation, alert delivery, monitoring availability |

Count business success per unique job, spending/retries per attempt. A dedicated bounded DB exporter samples queues every 15–30 seconds so multiple APIs do not duplicate backlog. Exporter failure/staleness has its own signal; old values must not look current.

Separate stage duration from queue wait. Unknown cost stays unknown, with missing-cost coverage reported. User edit counts alone are not quality failures: users can change their preferences.

### Dashboards and health

Initial dashboards: System health, Queues and workers, AI and cost, Rendering and quality, PostgreSQL and NAS. Private job pages link to versions, agent audit, reports and traces.

- `/livez` checks process liveness without depending on external AI.
- API `/readyz` checks request readiness, PostgreSQL and schema compatibility.
- Report NAS, AI and render-resource availability by capability; AI outages must not block state viewing.
- Workers report heartbeat and queue-specific readiness. Health checks never make a paid AI call.
- Restrict `/metrics` and administrative pages to authenticated operators/monitoring or a private network.

## 5. Service objectives and alerts

These are initial design targets, not measured guarantees for one NAS. Record hardware, input profile and supported concurrency after the first deployment. SLOs apply within those limits; throttle excessive load.

| Measure | Initial target / method |
|---|---|
| API availability | 99.5% over rolling 30 days via independent user-read checks; report planned maintenance separately |
| API latency | p95 ≤500 ms for metadata requests, excluding media transfer, SSE lifetime and AI execution |
| Job start | Runnable-job p95 wait: io ≤30 s, ai ≤120 s, render ≤300 s at stated load |
| Processing success | ≥99% of accepted supported projects before a profile-specific deadline, including provider/system failures |
| Search | Initial ANN recall@10 ≥0.95 versus exact search over identical eligible candidates |
| Integrity | Zero publication of unauthorized, unverified or cancelled data; violations block release |
| Backups | Initial RPO ≤24 h, RTO ≤4 h, confirmed by full-project restoration at measured size |

Success uses the cohort of accepted runs completed by deadline. Stuck jobs past deadline fail even without failed status. Explicit user cancellation and pre-acceptance unsupported formats are reported separately. Establish size/duration-profile deadlines from measurements before release.

Render throughput is conditional on output duration, resolution, effects and hardware; there is no universal deadline for arbitrary footage. Small samples display event counts and uncertainty rather than confident percentages/percentiles.

| Alert | Initial condition | Operator response |
|---|---|---|
| API / database unavailable | Three consecutive failed checks, 30 s apart | Inspect service/DB/network and preserve diagnostics before restart |
| Queue without workers | Runnable work and no healthy eligible worker for >2 min | Restore worker/dependency; inspect expired leases |
| No job progress | Stage deadline exceeded or expected progress absent | Inspect FFmpeg/AI/S3; cancel attempt through normal controls |
| NAS / scratch filling | <15% free warning, <5% critical, considering growth | Limit new work and verify safe cleanup/expansion |
| AI failure surge | >10% errors across ≥20 calls in 10 min, or repeated control-probe failures | Check quota/provider, limit calls; use only explicit fallback routes |
| Spending | 80% budget warning, 100% stops new paid work | Inspect retries/profile; finalize a valid available result |
| Invalid renders | ≥3 failed results in 15 min | Compare builds/presets, disable affected version, retain a sample |
| Overdue backup | No successful copy for >26 h under daily policy | Inspect destination, back up and verify recoverability |
| Silent monitoring | Independent observer misses heartbeat for >5 min | Check server and delivery path |

Use hold times, cause grouping and recovery notifications. Group many worker errors caused by one NAS outage. Define a notification channel and responsible operator during deployment; an environment without tested delivery is not fully operated.

An independent monitoring heartbeat runs on another host/NAS/service: a failed server cannot report its own outage. These requirements do not create actual schedules or notifications.

## 6. Test layers

| Layer | Tools | Scope |
|---|---|---|
| Unit | pytest, Vitest | Plan validation, time calculations, chat operations, budget, UI state |
| Property | Hypothesis | Ranges, speed/overlap, repeated operations, state transitions |
| Integration | Real PostgreSQL/pgvector, SeaweedFS, FFmpeg | Transactions, concurrency, S3, migrations, publication, recovery |
| Contract | Adapter fixtures plus bounded real API runs | Provider/catalog schemas, errors, file expiry, limits, compatibility |
| End-to-end | Playwright with backend/storage | Upload → film → edit → version → export, playback/cancellation |
| Media regression | FFmpeg/ffprobe, frames/audio markers | Transitions, audio, speed, titles, color, preview/export agreement |
| Load | k6 and job generator | HTTP/SSE, users, queue, fairness, resources, NAS |
| Fault/recovery | Controlled process termination, network/disk limits | Retries, leases, dependencies, backup restoration |
| AI quality | Versioned projects/briefs and human ratings | Compliance, script, music, effects, cost, time |
| Monitoring | promtool and delivery checks | Firing/resolution, missing data, grouping and delivery |

AI fixtures make routine tests reproducible but do not evaluate real model quality. S3 integrations use the selected SeaweedFS version, not just an emulator. Exercise races with independent connections/processes and synchronization barriers rather than random sleeps.

[Hypothesis](https://hypothesis.readthedocs.io/en/latest/) generates property cases, [Playwright](https://playwright.dev/docs/best-practices) checks visible behavior, [k6 thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/) gate load runs, and [promtool](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/) tests alert time series.

### Required scenarios

Each scenario needs a permanent test ID and observable assertion:

1. An identical request returns its existing result; changed content with the same ID conflicts.
2. Two workers cannot publish duplicate job results; a superseded lease token is rejected.
3. Concurrent edits to one version preserve edits without silent overwrites.
4. A crash after S3 PUT but before SQL commit is reconciled; retry creates no second current version.
5. Cancellation/deletion during upload, AI or rendering prevents late publication.
6. Ownership is enforced across routes, tools, search, SSE and signed links.
7. Multipart resumes after interruption; wrong hashes fail; renewed URLs recheck access.
8. NAS/DB outages, full scratch and provider unavailability preserve state with bounded retries.
9. Queues survive restarts; an overloaded project cannot starve others.
10. Missing resources, unknown effects and invalid ranges never reach rendering.
11. “Keep this whole,” “remove this moment,” and “change music, keep the edit” hold in plan and media.
12. Version switching/restoration, page refresh and SSE reconnect show actual state.
13. Filenames, titles, prompts and model output cannot inject executable FFmpeg/shell text.
14. Invalid JSON, refusals, unknown tools, input prompt injection, endless steps and budget exhaustion are bounded.
15. Temporary-file cleanup preserves retained-version and other-project resources.
16. Independent backup restoration recovers source/version/export playback and matching hashes.

## 7. Coverage and fixtures

| Area | Lines | Branches |
|---|---:|---:|
| Backend overall | ≥80% | ≥75% |
| Critical access/publication/leases/versions/plans/budget | ≥90% | ≥90% |
| Frontend overall | ≥80% | ≥70% |
| New/changed business logic | ≥90% | ≥80%; critical code ≥90% |

These are target release floors. Measure backend with pytest-cov/coverage.py and frontend with Vitest coverage. Keep line and branch results separate. Merge coverage across worker/API subprocesses and include application files never imported. Explicitly exclude generated code/dependencies, not domain errors/adapters to improve the number.

Critical invariants need success, failure and concurrency cases where relevant regardless of percentage. Selected mutation tests expose weak assertions. JSON snapshots/internal-call checks do not replace outcome checks. Coverage is not artistic quality.

Generate reproducible small fixtures with color fields, frame counters, known audio markers, speech, silence, portrait orientation, VFR and corrupt/truncated files. Store permitted real material in a private S3 evaluation set, with versioned manifests containing IDs, hashes, expected properties and usage terms. Do not copy production user footage into CI.

Frame/audio comparisons use tolerances; MP4 byte identity across encoders is not universal. Review golden changes substantively. Flaky tests get a cause, owner and repair deadline; reruns retain initial failures, and critical tests cannot be removed from release gates.

## 8. Agent and search evaluation

[Agent evaluation](agent-evaluation.md) defines formulas, numerators/denominators, sources, targets, labels and charts. Arbitrary “AI scores” are not substitutes for defined measurements.

Director metrics cover weighted events and repetition; music metrics cover human fit, speech and provenance; editor metrics cover defective boundaries, speech truncation and constraints; reviewer metrics cover precision/recall and false alarms. Common measures include deadline success, first-plan validity, critical violations, p95 time, all-attempt cost and evaluation coverage.

Compare identical suite versions and show projects/cases/trials, counts, intervals and baseline differences. Bootstrap by source project, keeping related cases/trials together. Missing/not-applicable are not successes. Keep code/human/LLM series separate. The full evaluator stores runs/results in PostgreSQL and evidence in S3, with read-only Grafana aggregate views.

The initial exploratory set is 20–30 varied projects with at least three edit types; the more specific evaluation contract targets 30 independent projects. Separate development and holdout sets, and compare changes to models/prompts/tools/presets/search on identical inputs.

| Criterion | Evaluation |
|---|---|
| Technical validity | Published candidates pass deterministic checks; invalid proposals remain counted |
| Hard constraints | Zero violations of required/excluded scenes, access and preserved edits |
| Story/selection | Event coverage, repetition, instruction match and blind human comparison |
| Music/effects | Fit, speech/title readability, excessive effects and confirmed resources |
| Search | ANN recall versus exact, separately from human semantic relevance |
| Efficiency | Cost per project/input minute, calls/trials, readiness and budget exhaustion |

With fewer than ten eligible neighbors, recall@10 uses the actual reference count. Exact/ANN use identical owner/project/profile filters, including restrictive filters. High ANN recall does not establish semantic relevance.

Reviewers assist but are not sole release judges. Repeat creative cases, initially three trials, to measure variability. Record model/prompt IDs, settings, tool versions, inputs and spend; check model availability and response drift after updates.

Block release for hard violations, reproducible technical regressions, budget overruns or worse accepted retrieval metrics. Creative comparison requires no confirmed regression; small uncertain samples need expansion. Investigate >20% time/cost growth on identical hardware; intentional increases require an explicit product-profile decision.

## 9. CI and release gates

| Trigger | Required checks |
|---|---|
| Every PR | Formatting/lint/types, unit/property tests, coverage, critical PG/S3 integrations, short actual render, minimal Playwright with AI fixtures, migrations and monitoring rules |
| Prompt/model/preset change | Relevant AI/media control suite and baseline comparison |
| Extended recurring run | Larger media set, races, process/network faults, queue growth, soak run, bounded live AI smoke |
| Release candidate | Full matrix, reference-host load, restoration, alert delivery, migration from previous version and application rollback |
| After deployment | Small synthetic project, playback/download, metrics, queues and errors |

This is the complete target CI contract. The alpha's shipped workflow is a subset; no paid evaluations or recurring schedules are created by this document. Untrusted PRs receive no provider secrets. Live evaluations run in trusted environments with separate budgets and approved data. Pin database/extensions/SeaweedFS/FFmpeg/dependencies and scan dependencies, images and accidental secrets.

Artifacts include JUnit, separate line/branch coverage, AI evaluation, environment versions, load and restore reports. Retain sanitized failure logs, Playwright traces and small test excerpts with bounded retention.

Test migrations on empty databases and previous-version data copies. Use compatible rollout steps; application rollback must not require destructive data rollback. Lost plans, inability to render old versions and unexplained throughput loss block release.

Data/access/output defects receive reproducing tests. New effects require parameter, boundary, compatibility and actual-render tests. Alerts need an owner, diagnostic steps and recovery checks.

## 10. Operational checks

- Reconcile S3/database state for incomplete uploads, unpublished objects and missing resources under the retention policy.
- Store daily PostgreSQL/media backups outside the primary failure domain. Record a DB snapshot/recovery point and immutable-object manifest; garbage collection respects retained backups.
- Practice restoration monthly and before major storage changes. Record measured RPO/RTO, size, time, hashes and playback results.
- Preserve diagnostics before restoring dependencies or restarting an attempt through supported controls. Manually setting ready or deleting stuck SQL rows is not recovery.
- Protect DB/NAS/budgets with active-project/call/render limits, a shared provider limiter and preflight scratch checks.
- Adding hosts requires rechecking global limits, connection pools, fairness and observability; workers do not remove NAS throughput limits.

## 11. Implementation sequence and current status

1. First API/worker: error contracts, boundary validators, JSON logs, correlation IDs, metrics and minimal tests.
2. Upload/queue: real PG/SeaweedFS integrations, race/idempotency tests, dashboards, alerts and delivery.
3. First render: control media, validation before ready, timing/audio/resource checks and playback.
4. Agents: tool audit, budgets, evaluation suite, invalid-output tests and bounded revisions.
5. Release: coverage gates, end-to-end tests, load, restoration, migrations and demonstrated operating limits.

The original 31-condition single-connection PGlite experiment checked schema/SQL only. The alpha now has real service integrations and measured coverage in [local validation](local-validation.md). The broader targets above, including full evaluator, tracing, alert delivery and restore/load objectives, must not be presented as completed merely because routine CI passes.

## References

- [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/)
- [Prometheus instrumentation](https://prometheus.io/docs/practices/instrumentation/)
- [Alerting and Alertmanager](https://prometheus.io/docs/alerting/latest/overview/)
- [Prometheus rule tests](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [pytest fixtures](https://www.pytest.org/en/latest/explanation/fixtures.html)
- [Hypothesis](https://hypothesis.readthedocs.io/en/latest/)
- [Vitest coverage](https://vitest.dev/guide/coverage)
- [Playwright best practices](https://playwright.dev/docs/best-practices)
- [k6 thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
