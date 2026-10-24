# Deploying on your server or NAS

The alpha supports one owner. The server needs Docker Compose; processing can move from the NAS to a separate CPU host. PostgreSQL keeps data on its host's local disk, while SeaweedFS stores media on server/NAS storage. A successful local run does not verify a particular NAS model.

## First launch

1. Clone the repository and run `python3 scripts/configure.py`.
2. Set `MEDIA_ROOT=/srv/vmerger/media` in `.env` and add credentials for routes selected in `config/ai.toml`. Hosted APIs and self-hosted LLMs are supported. Store secrets in a password manager. MEDIA_ROOT must exist and be accessible to SeaweedFS.
3. Run `docker compose config --quiet`, then `docker compose up --build -d`.
4. Check `docker compose ps`, `curl -f http://127.0.0.1:8000/readyz`, and sign in with APP_TOKEN.
5. For SSH access without exposing the application port: `ssh -L 8000:127.0.0.1:8000 user@server`.

Database, S3, filer and master do not publish host ports. API binds to loopback by default. Services trust one another within the Docker network; do not attach unrelated containers.

The [self-hosting guide](self-hosted-llm.md) covers vLLM on your GPU or Vast.ai, native/Docker SSH tunnels and backup routes. Backups must already be running: the base Compose setup does not rent or release GPUs.

## HTTPS

Point the domain's DNS at the server, set DOMAIN in `.env`, expose ports 80/443 and run:

```sh
docker compose -f compose.yaml -f deploy/compose.server.yaml up --build -d
```

Caddy obtains a certificate. The API uses Secure cookies and requires the exact HTTPS Origin. Correct the domain/proxy configuration rather than disabling Origin validation.

## Scaling

```sh
docker compose up -d --scale worker=2
```

API memory is not the sole state store. Workers claim PostgreSQL jobs. Separate pools can run `python -m vmerger.worker --queues ai` and `--queues render`. Measure memory, CPU, scratch and S3 throughput before increasing FFmpeg concurrency. SeaweedFS mini is currently single-node without replication. Distributed SeaweedFS/S3 can replace it behind the same application interface.

## Monitoring

Run `docker compose --profile monitoring up -d`. Grafana and Prometheus remain on loopback. Grafana provisions **VMerger · Operations**; Prometheus checks API unavailability, queues older than ten minutes and provider failures. Alertmanager/outbound notifications are not configured. The application's Quality tab shows per-story observations. UUIDs and filenames are not metric labels.

## Backup and restore

For a simple consistent alpha backup, stop API/worker with `docker compose stop api worker`, create a custom-format `pg_dump` from the database container and snapshot/copy **all of MEDIA_ROOT**, including filer metadata. Restart services afterward. SeaweedFS volume files without metadata are not a complete backup. Keep an encrypted copy off-server and preserve secrets and code version separately.

Test restoration on an empty independent installation: restore the dump and complete SeaweedFS directory, start the same code version, check readiness/sign-in, read sources, verify hashes, play old versions and produce a new render. Apply later migrations afterward. **RPO/RTO are unmeasured**; values in the operations design are targets.

## Updates and maintenance

Stop API/worker, back up, fetch the new commit, rebuild, run init and restart services. Workers do not run migrations concurrently. There is no automatic destructive downgrade; recover using a verified backup.

`docker compose run --rm api python -m vmerger.cleanup` deletes only failed objects unreferenced by assets/renders/derivatives. Objects left writing after crashes need investigation. Full project deletion/retention is not implemented; address this before sustained multi-user operation.
