# Native Windows setup without Docker

Requires Python 3.12, Node.js 22+, pnpm 11.25.0 and Visual Studio Build Tools with C++ desktop development. Binaries/data live in ignored `.local`; no system services are installed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe scripts/configure.py
.\.venv\Scripts\python.exe scripts/bootstrap_windows.py
```

Set an unused PostgreSQL port, such as `55432`, in `.env`'s DATABASE_URL. configure.py generates passwords; do not replace them with a placeholder such as `change-me`.

```powershell
.\.venv\Scripts\python.exe scripts/start_native.py
.\.venv\Scripts\python.exe -m vmerger.initialize
pnpm --dir web install --frozen-lockfile
pnpm --dir web run build
.\.venv\Scripts\python.exe -m uvicorn vmerger.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```powershell
.\.venv\Scripts\python.exe -m vmerger.worker
```

Open http://127.0.0.1:8000 and enter APP_TOKEN from `.env`. Without configured AI credentials, the interface reports unavailable roles while uploads continue working. Choose providers/models in `config/ai.toml`; add their keys later, restart API/worker and analyze existing sources. Self-hosted endpoints are also supported; see [providers](providers.md).

For Vite development, set `APP_ORIGIN=http://127.0.0.1:5173`, restart the API and run `pnpm --dir web run dev`. The API remains on port 8000; Vite proxies `/api`. Restore APP_ORIGIN to port 8000 for the built application.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest --integration --cov=vmerger --cov-report=json:.local/coverage.json
.\.venv\Scripts\python.exe scripts/check_coverage.py
pnpm --dir web run test
$env:PLAYWRIGHT_CHANNEL='chrome'
pnpm --dir web exec playwright test
```

The browser check uses installed Chrome and a running API with live AI disabled. It creates an empty **Local validation** project; docs/images contains actual interface screenshots. Media tests use explicitly labeled color clips/signals, not invented AI results.

## Shutdown

Stop API and worker with Ctrl+C in their terminals. Stop PostgreSQL with:

```powershell
& .local/tools/postgres/pgsql/bin/pg_ctl.exe -D .local/pgdata stop -m fast
```

SeaweedFS runs in the background with its PID in `.local/seaweed.pid`. Verify that PID belongs to `.local/tools/weed/weed.exe` before stopping it. Do not delete `.local/seaweed` or `.local/pgdata`: they contain persistent data.

Downloaded versions and SHA-256 values are pinned in bootstrap_windows.py. Sources: [EDB PostgreSQL binaries](https://www.enterprisedb.com/download-postgresql-binaries), [pgvector](https://github.com/pgvector/pgvector), [SeaweedFS releases](https://github.com/seaweedfs/seaweedfs/releases), [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/). These are third-party dependencies; executables are not committed.
