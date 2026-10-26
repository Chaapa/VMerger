# Testing

The test suite separates deterministic provider fixtures from real service integration. Provider fixtures check orchestration and API contracts; they do not measure the editing quality of live models.

## Fast checks

From a Python 3.12 virtual environment:

```sh
python -m pip install -r requirements.lock
python scripts/configure.py
python -m pytest
ruff check vmerger migrations tests
pnpm --dir web install --frozen-lockfile
pnpm --dir web run build
pnpm --dir web run test
```

`configure.py` creates the local settings required by the tests; it preserves an existing `.env`. By default, pytest skips tests marked `integration`. The remaining tests cover plan constraints, normalized vectors, provider configuration, structured responses and failure/fallback handling.

## Service integration

Start PostgreSQL, S3 and the application with [Docker](../README.md#run-locally) or the [native Windows setup](local-setup.md). For a host-side test runner, the disposable Compose override exposes PostgreSQL and S3 on loopback:

```sh
python scripts/configure.py
docker compose -f compose.yaml -f deploy/compose.ci.yaml up --build -d api worker
python -m pytest --integration --cov=vmerger --cov-report=json:.local/coverage.json
python scripts/check_coverage.py
```

The test runner must have FFmpeg and ffprobe on PATH, or `FFMPEG_BIN` and `FFPROBE_BIN` configured. Use an isolated test deployment. Tests create a separate PostgreSQL schema, apply Alembic migrations and clean up their own schema and S3 objects.

The integration suite exercises:

- Authentication, project boundaries and byte-range playback.
- Upload validation, stored-byte verification, deduplication and music rights.
- Rendering generated fixture clips with and without audio through real FFmpeg.
- Concurrent claims, expired leases, cancellation and stale-version publication.
- Embedding profile changes, reindex deduplication and preservation of old profiles.
- Provider audit records, including a failed primary followed by a successful backup.

No paid provider call is required by this suite.

## Browser smoke test

With the API running and live AI credentials disabled:

```sh
pnpm --dir web exec playwright install chromium
pnpm --dir web exec playwright test
```

The test creates an empty project named **Local validation**, checks sign-in and workspace controls, and captures desktop/mobile layouts and themes. Screenshots are written to `docs/images/`. It does not demonstrate a live AI-generated film.

## CI and coverage

The [Verify workflow](../.github/workflows/ci.yml) builds the Linux Compose stack and runs Python integration tests in the application container, frontend checks, browser smoke tests and monitoring checks. It uploads coverage and browser artifacts as `validation-evidence`.

The workflow enforces at least 85% combined coverage. [`check_coverage.py`](../scripts/check_coverage.py) separately enforces 80% statement / 75% branch coverage overall and 90% statement / 80% branch coverage for contracts and jobs. These are different measures; a single combined percentage does not establish either component.

## Historical validation

The [report recorded at d0f337d](https://github.com/Chaapa/VMerger/blob/d0f337da1c82bde9c5d5444b262b19521953608f/docs/local-validation.md), dated October 24, 2026, lists 74 passing Python tests including integrations, 93.74% statement coverage, 84.67% branch coverage, three passing frontend tests and one passing Chrome smoke test. It used native PostgreSQL, SeaweedFS and FFmpeg on Windows. These are historical results, not a fresh run of the current revision; consult the [commit's CI run](https://github.com/Chaapa/VMerger/actions/workflows/ci.yml) for current status.

## Evaluation still needed

Use permitted footage and explicitly selected live providers to evaluate scene accuracy, pacing, music fit and whether revisions follow the request. Keep provider judgments separate from human ratings and hard validation. Record model/configuration versions and count independent source projects when comparing results.

Live-model quality, retrieval recall on a labeled dataset, load limits and backup restoration times remain unmeasured. Operational metrics and their limits are documented in [operations](operations.md).
