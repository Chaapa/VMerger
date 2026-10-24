# VMerger PostgreSQL schema validation

Date: October 23, 2026. Files checked: schema.sql and worker-and-search.sql.

This records the earlier SQL-only experiment. Later real PostgreSQL, S3, FFmpeg and application checks are in [local validation](local-validation.md). The broader validation/monitoring/coverage/CI plan is in [quality and operations](quality-and-operations.md). Targets are not automatically passed checks; measured results are reported separately.

Environment: PGlite 0.5.11 (PostgreSQL 18 in WebAssembly), pgvector 0.8.7, one connection and a temporary in-memory database. No PostgreSQL server or NAS was deployed for this experiment.

**31 assertions passed**, covering:

- Creation of 16 tables, extension, indexes and prepared queries.
- External-identity uniqueness and prevention of deleting an owner with projects.
- Required verified-object metadata, within-project source deduplication and project independence.
- Project-scoped object/source/segment/upload-result references.
- Upload completion requiring a result and request-ID deduplication.
- Positive ranges and automatic PostgreSQL full-text index updates.
- Vector dimension/normalization, exact ranking and owner/project/profile filters.
- ANN query execution and scope. This small set does not establish HNSW performance or recall.
- Version immutability, compare-and-swap, stale-base rejection and rejection of another story's version.
- Ready renders requiring object reference, duration and completion time.
- Job deduplication, queue selection and exclusion of already claimed work during sequential claims.
- Wrong-token rejection, lease expiry, fresh retry tokens and rejection of old tokens.
- Attempt exhaustion, queued cancellation and cleanup-only work for deleting projects.
- Cascading project metadata deletion preserving another owner's data.

The experiment found and fixed cascade-order failure: cross-references between deleted entities are deferred until transaction end. Invalid relationships still fail at commit.

It did not test true concurrent PostgreSQL connections, another process skipping a locked row, load, pooling, HTTP authentication, service publication rules, S3 or AI. Sequential token checks over PGlite's single connection do not establish distributed correctness.

Release validation requires pinned server integrations with two workers, lease expiry during rendering, concurrent edits and deletion/publication races; p95/recall measurements; S3 failures and backup restoration. Earlier SQLite checks do not validate this PostgreSQL schema.
