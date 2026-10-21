"""Start pre-installed portable Windows dependencies, bound to loopback only."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from vmerger.config import settings  # noqa: E402

s = settings()
local = ROOT / ".local"
pg = local / "tools/postgres/pgsql/bin"
data = local / "pgdata"
dsn = urlparse(s.database_url)
password_file = local / "pg-password"
password_file.write_text(dsn.password, encoding="utf-8")
try:
    if not (data / "PG_VERSION").exists():
        subprocess.run([str(pg / "initdb.exe"), "-D", str(data), "-U", dsn.username,
                        "--pwfile", str(password_file), "--auth=scram-sha-256", "--encoding=UTF8",
                        "--locale=C"], check=True)
finally:
    password_file.unlink(missing_ok=True)
status = subprocess.run([str(pg / "pg_ctl.exe"), "-D", str(data), "status"], capture_output=True)
if status.returncode:
    subprocess.run([str(pg / "pg_ctl.exe"), "-D", str(data), "-l", str(local / "postgres.log"),
                    "-o", f"-h 127.0.0.1 -p {dsn.port or 5432}", "start"], check=True)
import psycopg  # noqa: E402
with psycopg.connect(s.database_url.rsplit("/", 1)[0] + "/postgres", autocommit=True) as conn:
    name = dsn.path[1:]
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
        from psycopg import sql
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

config = local / "s3.json"
config.write_text(json.dumps({"identities": [{"name": "vmerger", "credentials": [{
    "accessKey": s.s3_access_key, "secretKey": s.s3_secret_key}], "actions": ["Admin", "Read", "Write"]}]}))
storage = local / "seaweed"
storage.mkdir(exist_ok=True)
import socket  # noqa: E402
with socket.socket() as sock:
    running = sock.connect_ex(("127.0.0.1", 8333)) == 0
if not running:
    log = (local / "seaweed.log").open("ab")
    process = subprocess.Popen([str(local / "tools/weed/weed.exe"), "mini", f"-dir={storage}",
        "-ip=127.0.0.1", "-ip.bind=127.0.0.1", "-s3.port=8333", f"-s3.config={config}",
        "-admin.ui=false", "-webdav=false", "-volume.max=4"],
        stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    (local / "seaweed.pid").write_text(str(process.pid))
ffmpeg = next((local / "tools/ffmpeg").glob("*/bin/ffmpeg.exe"))
env_path = ROOT / ".env"
lines = env_path.read_text().splitlines()
for key, value in [("FFMPEG_BIN", ffmpeg), ("FFPROBE_BIN", ffmpeg.with_name("ffprobe.exe"))]:
    lines = [f"{key}={value.as_posix()}" if line.startswith(key + "=") else line for line in lines]
env_path.write_text("\n".join(lines) + "\n")
print("Native services started; PostgreSQL and S3 are bound to loopback.")
