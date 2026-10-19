from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from vmerger import jobs, pipeline
from vmerger.config import settings
from vmerger.contracts import Analysis, MusicChoice, ProjectPlan, Review, Scene, StoryPlan
from vmerger.db import connect, enqueue, jsonb

pytestmark = pytest.mark.integration


class FixtureProvider:
    """Deterministic contract fixture; never presented as an AI quality benchmark."""

    def __init__(self, job):
        self.job = job

    def analyze(self, path, duration):
        assert path.exists() and path.stat().st_size > 0
        return Analysis(scenes=[Scene(start=0, end=min(duration, 1.5), description="Fixture beach scene")])

    def embed(self, texts, query=False):
        return [[1.0] + [0.0] * 767 for _ in texts]

    def call(self, role, prompt, schema):
        assets = pipeline.assets_for(self.job["project_id"])
        clips = [
            {"asset_id": key, "start": 0, "end": 1.0, "effect": "warm"}
            for key, value in assets.items()
            if value["kind"] == "video"
        ]
        plan = StoryPlan(title="Fixture story", summary="Test-only output", clips=clips)
        if role == "director":
            return ProjectPlan(stories=[plan])
        if role == "editor":
            return plan
        if role == "music":
            audio = next((k for k, v in assets.items() if v["kind"] == "audio"), None)
            return MusicChoice(music_asset_id=audio, rationale="Fixture selection")
        return Review(approved=True, issues=[])


def drain():
    while job := jobs.claim():
        pipeline.process(job, FixtureProvider)


def test_real_pipeline_roundtrip_versions_and_metrics(client, project, videos, monkeypatch):
    paths, music = videos
    prefix = f"/api/projects/{project['id']}"
    for path in paths:
        response = client.post(prefix + "/assets?name=" + path.name, content=path.read_bytes())
        assert response.status_code == 201, response.text
    audio = client.post(
        prefix + "/assets?name=fixture.wav&license_note=Generated+test+signal", content=music.read_bytes()
    )
    assert audio.status_code == 201, audio.text
    monkeypatch.setattr(settings(), "gemini_api_key", "test-fixture-no-network")
    assert client.post(prefix + "/analyze").status_code == 202
    drain()
    snapshot = client.get(prefix).json()
    assert all(a["status"] == "ready" for a in snapshot["assets"])
    assert len(client.get(prefix + "/search?q=beach").json()) == 2
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) n FROM segment_embeddings WHERE project_id=%s", (project["id"],)
            ).fetchone()["n"]
            == 2
        )
    command = {"text": "Create a fixture story", "request_id": str(uuid4())}
    first = client.post(prefix + "/messages", json=command)
    assert first.status_code == 202, first.text
    assert client.post(prefix + "/messages", json=command).json()["id"] == first.json()["id"]
    assert client.post(prefix + "/messages", json={**command, "text": "Different command"}).status_code == 409
    drain()
    snapshot = client.get(prefix).json()
    assert len(snapshot["stories"]) == 1
    story = snapshot["stories"][0]
    assert story["status"] == "ready"
    render = snapshot["renders"][0]
    media_url = prefix + "/objects/" + render["storage_object_id"]
    output = client.get(media_url)
    assert output.status_code == 200 and len(output.content) > 1000
    partial = client.get(media_url, headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206 and len(partial.content) == 100
    assert client.get(media_url, headers={"Range": "invalid"}).status_code == 416
    revision = {
        "text": "Make it warmer",
        "request_id": str(uuid4()),
        "story_id": story["id"],
        "context_version_id": story["current_version_id"],
    }
    assert client.post(prefix + "/messages", json=revision).status_code == 202
    drain()
    snapshot = client.get(prefix).json()
    assert len(snapshot["edit_versions"]) == 2
    assert len(snapshot["renders"]) == 2
    assert snapshot["stories"][0]["current_version_id"] != story["current_version_id"]
    revision["request_id"] = str(uuid4())
    assert client.post(prefix + "/messages", json=revision).status_code == 409
    assert any(e["metric"] == "decode_pass" and e["value"] == 1 for e in snapshot["eval_results"])
    assert b"vmerger_jobs" in client.get("/api/metrics").content
    assert client.get("/readyz").status_code == 200


def test_auth_csrf_and_cross_project_scope(client, project):
    from fastapi.testclient import TestClient

    from vmerger.api import app

    with TestClient(app) as anonymous:
        assert anonymous.get("/api/projects").status_code == 401
        assert anonymous.post("/api/projects", json={"title": "Blocked"}).status_code == 403
        assert (
            anonymous.post(
                "/api/session",
                headers={"Origin": settings().app_origin, "X-VMerger-Request": "1"},
                json={"token": "wrong"},
            ).status_code
            == 401
        )
    with connect() as conn:
        stranger = conn.execute(
            "INSERT INTO users(auth_issuer,auth_subject) VALUES ('test',%s) RETURNING id", (str(uuid4()),)
        ).fetchone()["id"]
        hidden = conn.execute(
            "INSERT INTO projects(owner_id,title) VALUES (%s,'Private') RETURNING id", (stranger,)
        ).fetchone()["id"]
    prefix = f"/api/projects/{hidden}"
    assert client.get(prefix).status_code == 404
    assert client.get(prefix + "/search?q=beach").status_code == 404
    assert client.get(prefix + f"/objects/{uuid4()}").status_code == 404
    assert client.post(prefix + "/assets?name=test.mp4", content=b"x").status_code == 404


def test_upload_validation_and_dedup(client, project, videos, monkeypatch):
    prefix = f"/api/projects/{project['id']}"
    path = videos[0][0]
    first = client.post(prefix + "/assets?name=test.mp4", content=path.read_bytes())
    second = client.post(prefix + "/assets?name=again.mp4", content=path.read_bytes())
    assert first.json()["id"] == second.json()["id"]
    assert client.post(prefix + "/assets?name=empty.mp4", content=b"").status_code == 422
    assert client.post(prefix + "/assets?name=invalid.mp4", content=b"not a video").status_code == 422
    assert (
        client.post(prefix + "/assets?name=unlicensed.wav", content=videos[1].read_bytes()).status_code == 422
    )
    monkeypatch.setattr(settings(), "max_upload_mb", 0)
    assert client.post(prefix + "/assets?name=oversize.mp4", content=path.read_bytes()).status_code == 413
    assert (
        client.post(prefix + "/messages", json={"text": "Edit", "request_id": str(uuid4())}).status_code
        == 503
    )


def test_queue_concurrency_fencing_retry_and_cancellation(database, project):
    with connect() as conn:
        for _ in range(8):
            enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
    with ThreadPoolExecutor(max_workers=8) as executor:
        claimed = list(executor.map(lambda _: jobs.claim(), range(8)))
    assert len({j["id"] for j in claimed}) == 8
    assert jobs.claim() is None
    stale = claimed[0]
    with connect() as conn:
        conn.execute("UPDATE jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s", (stale["id"],))
    replacement = jobs.claim()
    assert replacement["id"] == stale["id"] and replacement["lease_token"] != stale["lease_token"]
    assert not jobs.heartbeat(stale)
    with connect() as conn, pytest.raises(jobs.LeaseLost):
        jobs.fence(conn, stale)
    with connect() as conn:
        jobs.fence(conn, replacement)
        jobs.succeed(conn, replacement)
    for job in claimed[1:]:
        with connect() as conn:
            conn.execute("UPDATE jobs SET cancel_requested=true WHERE id=%s", (job["id"],))
        assert not jobs.heartbeat(job)
        jobs.fail(job, RuntimeError())
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) n FROM jobs WHERE project_id=%s AND status='cancelled'", (project["id"],)
            ).fetchone()["n"]
            == 7
        )
        waiting = enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
        conn.execute("UPDATE jobs SET cancel_requested=true WHERE id=%s", (waiting["id"],))
    assert jobs.claim() is None


def test_database_rejects_cross_project_reference_and_version_mutation(client, project):
    import psycopg

    other = client.post("/api/projects", json={"title": "Other"}).json()
    with connect() as conn:
        story = conn.execute(
            "INSERT INTO stories(project_id,title) VALUES (%s,'Story') RETURNING id", (project["id"],)
        ).fetchone()["id"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation), connect() as conn:
        conn.execute(
            "INSERT INTO edit_versions(project_id,story_id,revision,plan,plan_hash,schema_version) VALUES (%s,%s,1,%s,'x',1)",
            (other["id"], story, jsonb({})),
        )
    with connect() as conn:
        version = conn.execute(
            "INSERT INTO edit_versions(project_id,story_id,revision,plan,plan_hash,schema_version) VALUES (%s,%s,1,%s,'x',1) RETURNING id",
            (project["id"], story, jsonb({})),
        ).fetchone()["id"]
    with pytest.raises(psycopg.errors.RaiseException), connect() as conn:
        conn.execute("UPDATE edit_versions SET plan_hash='changed' WHERE id=%s", (version,))
