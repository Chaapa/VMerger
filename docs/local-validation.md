# Measured local validation

Date: October 24, 2026, after English UI/documentation updates. Environment: Windows, Python 3.12.14, PostgreSQL 18.6, pgvector 0.8.7, SeaweedFS 4.49, FFmpeg 8.1.2 and installed Chrome. PostgreSQL/SeaweedFS run natively on loopback. Persistent media lives in SeaweedFS S3.

## Results

| Check | Observed result |
|---|---|
| pytest including integrations | **74 passed**, 51.83 s, including explicit empty credentials as in Compose |
| Python line coverage | **959 / 1023 = 93.74%** |
| Python branch coverage | **232 / 274 = 84.67%** |
| coverage.py combined figure | 91.83%; distinct from line coverage |
| Plan contracts | 100% lines and branches |
| Vitest metric calculations | **3 passed** |
| TypeScript / production build | Passed |
| Playwright / Chrome | **1 passed**: sign-in, project, AI roles, empty metrics, light/dark, 1440px and 390px |
| Ruff / git diff --check | Passed |
| Mermaid across README and documentation | **12 diagrams** parsed/rendered |
| Python wheel | Built in an isolated build environment, including MIT LICENSE |

The English browser check used an isolated PostgreSQL schema and a temporary API on port 8001. Screenshots show the real application with an explicitly labeled empty test project; the schema was removed afterward. Desktop and mobile layouts were inspected. A repository text scan found no remaining Cyrillic UI/documentation strings or Russian locale declarations. Existing user-entered project content is not translated by this change. The wheel check above was performed during the preceding MIT-license change.

The end-to-end integration generates two fixture clips, with and without audio, and a test music track with rights confirmation. It uploads through HTTP, verifies S3 and runs the pipeline with a deterministic provider fixture. Real FFmpeg assembles and fully decodes output, which is stored in S3 and served over HTTP. A second version and Range responses are checked. This verifies plan execution, **not live-model quality**.

Additional checks cover CSRF/sign-in, cross-project access, corrupt/empty/oversized uploads, deduplication, unconfirmed music rights, forbidden effects, out-of-bounds intervals, invalid embedding dimensions/NaN/zero norm, immutable versions and project-scoped foreign keys.

The concurrency test uses eight independent PostgreSQL connections so one job cannot be handed to two workers. It checks token rotation after expiry, stale-publication rejection, heartbeat after cancellation, retry exhaustion and an actual stale render that cannot replace a newer version.

Gemini SDK and compatible HTTP fixtures verify response structure, token/time accounting and secret-free error records. They cover mixed role endpoints, configuration snapshots, refused/truncated answers, timeouts, 429/5xx, reordered/invalid embeddings, prefixes and secret-free public settings. These tests make no external model calls.

Fallback tests cover timeout, connection failure, 429/503 and Gemini SDK errors, ordered backups and exhaustion. They reject switching on 400/401, missing credentials, refusal, invalid/truncated output and audit/database failure. PostgreSQL integration preserves a failed primary and successful backup with distinct provider/model/fingerprint. Configuration rejects missing/duplicate routes, more than two backups and analyst/embedding fallback. The full hybrid example parses successfully. No real GPU, vLLM or Vast.ai instance was launched.

Reindex integration changes the embedding model: search returns 409 until reindexing, repeated requests deduplicate active jobs, old profiles survive, the new profile becomes searchable and repeat indexing does not duplicate scenes. Profile changes before execution are detected. Another test extracts real JPEG frames through FFmpeg; frame-only analysis rejects invented speech.

## Issues found and fixed

- Windows proxy inheritance broke local S3; explicitly configured S3 endpoints now disable inherited HTTP proxies.
- Test search_path could find shared alembic_version and skip migration; the version table is schema-scoped, and setup verifies current_schema plus empty tables.
- Music/edit decisions across multiple stories must accumulate denominators instead of resetting to one.
- Vitest must not collect Playwright scenarios; configuration separates the suites.
- Compose explicitly injects empty `GEMINI_API_KEY`. Tests override environment credentials and verify that empty environment values override `.env` and cached settings.

## Not yet demonstrated

Live AI calls remain disabled at the owner's request. Artistic quality, reviewer precision/recall, labeled retrieval recall, costs, load SLA, RPO/RTO and a real NAS deployment are unmeasured. Docker is not installed locally; Linux Compose validation runs in [GitHub Actions](https://github.com/Chaapa/VMerger/actions/workflows/ci.yml). Check the status for the specific commit.

Reaching 90% branch coverage in all critical modules and covering all user workflows remain goals. Passing the current 80% line /75% branch floors does not make the alpha production-ready. pytest reports one installed-Starlette TestClient/httpx deprecation warning; checks pass.

The original [31 PGlite SQL assertions](validation.md) remain a separate early experiment, not a replacement for service integrations.
