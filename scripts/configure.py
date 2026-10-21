"""Generate local deployment secrets and private service configuration, without printing secrets."""
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if not path.exists():
    text = (root / ".env.example").read_text()
    password = secrets.token_urlsafe(24)
    text = text.replace("vmerger:change-me@", f"vmerger:{password}@")
    text = text.replace("S3_SECRET_KEY=change-me", "S3_SECRET_KEY=" + secrets.token_urlsafe(32))
    text = text.replace("APP_TOKEN=\n", "APP_TOKEN=" + secrets.token_urlsafe(32) + "\n")
    path.write_text(text)
values = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))
if not values.get("POSTGRES_PASSWORD"):
    with path.open("a") as stream:
        stream.write("\nPOSTGRES_PASSWORD=" + urlparse(values["DATABASE_URL"]).password + "\n")
local = root / ".local"
local.mkdir(exist_ok=True)
(local / "s3.json").write_text(json.dumps({"identities": [{"name": "vmerger", "credentials": [{
    "accessKey": values["S3_ACCESS_KEY"], "secretKey": values["S3_SECRET_KEY"]}], "actions": ["Admin", "Read", "Write"]}]}))
(local / "metrics-token").write_text(values["APP_TOKEN"])
print("Created private configuration in .env and .local/. Keep both out of Git.")
