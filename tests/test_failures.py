import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from vmerger import jobs, pipeline, worker
from vmerger.config import settings
from vmerger.contracts import Review, StoryPlan
from vmerger.db import connect, enqueue, jsonb
from vmerger.providers import ProviderRouter

pytestmark = pytest.mark.integration


def test_retry_budget_and_stale_publication(project):
    with connect() as conn:
        enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
    for attempt in range(1, 4):
        job = jobs.claim()
        assert job["attempt"] == attempt
        jobs.fail(job, TimeoutError(), retry=True)
        with connect() as conn:
            conn.execute("UPDATE jobs SET available_at=now() WHERE id=%s", (job["id"],))
    assert jobs.claim() is None
    with connect() as conn:
        assert (
            conn.execute("SELECT status FROM jobs WHERE id=%s", (job["id"],)).fetchone()["status"] == "failed"
        )
        with pytest.raises(jobs.LeaseLost):
            jobs.fence(conn, job)


def test_heartbeat_detects_cancellation(project, monkeypatch):
    with connect() as conn:
        enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
    job = jobs.claim()
    assert jobs.heartbeat(job)
    monkeypatch.setattr(settings(), "lease_seconds", 3)
    with jobs.keep_alive(job) as lost:
        with connect() as conn:
            conn.execute("UPDATE jobs SET cancel_requested=true WHERE id=%s", (job["id"],))
        assert lost.wait(3)
    jobs.fail(job, RuntimeError())


def test_worker_failure_keeps_history_and_metrics(project, monkeypatch):
    def reject(job):
        raise ValueError("Fixture rejection")

    monkeypatch.setattr(worker, "process", reject)
    with connect() as conn:
        job = enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
    assert worker.run_once()
    assert not worker.run_once()
    with connect() as conn:
        assert (
            conn.execute("SELECT status FROM jobs WHERE id=%s", (job["id"],)).fetchone()["status"] == "failed"
        )
        assert (
            conn.execute("SELECT value FROM eval_results WHERE job_id=%s", (job["id"],)).fetchone()["value"]
            >= 0
        )


def test_provider_adapter_records_success_and_failure_without_network(project, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    with connect() as conn:
        enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
    job = jobs.claim()

    class Models:
        def generate_content(self, **kwargs):
            assert kwargs["config"].response_json_schema
            return SimpleNamespace(
                text=json.dumps({"approved": True, "issues": []}),
                usage_metadata=SimpleNamespace(prompt_token_count=30, candidates_token_count=12),
            )

        def embed_content(self, **kwargs):
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[2.0] + [0.0] * 767)])

    monkeypatch.setattr("vmerger.providers.genai.Client", lambda **kw: SimpleNamespace(models=Models()))
    provider = ProviderRouter(job)
    assert provider.call("reviewer", "Fixture prompt", Review).approved
    assert provider.embed(["fixture"])[0][0] == 1
    assert provider.embed(["fixture"], query=True)[0][0] == 1

    def fail(**kwargs):
        raise TimeoutError("Do not store this provider body")

    monkeypatch.setattr(provider.adapter("reviewer").client.models, "generate_content", fail)
    with pytest.raises(TimeoutError):
        provider.call("reviewer", "Fixture prompt", Review)
    monkeypatch.setattr(provider.adapter("embedding").client.models, "embed_content", fail)
    with pytest.raises(TimeoutError):
        provider.embed(["fixture"])
    with connect() as conn:
        calls = conn.execute(
            "SELECT * FROM ai_calls WHERE job_id=%s AND purpose='reviewer' ORDER BY created_at", (job["id"],)
        ).fetchall()
        assert [c["status"] for c in calls] == ["succeeded", "failed"]
        assert calls[0]["input_tokens"] == 30
        assert calls[1]["error"] == {"type": "TimeoutError"}
        jobs.fence(conn, job)
        jobs.succeed(conn, job)


def test_stale_render_cannot_replace_current_version(client, project, videos):
    prefix = f"/api/projects/{project['id']}"
    path = videos[0][0]
    asset = client.post(prefix + "/assets?name=fixture.mp4", content=path.read_bytes()).json()
    plan = StoryPlan(title="Stale", summary="", clips=[{"asset_id": asset["id"], "start": 0, "end": 1}])
    with connect() as conn:
        story = conn.execute(
            "INSERT INTO stories(project_id,title) VALUES (%s,'Story') RETURNING id", (project["id"],)
        ).fetchone()["id"]
        versions = []
        for revision in (1, 2):
            versions.append(
                conn.execute(
                    """INSERT INTO edit_versions(project_id,story_id,revision,plan,
                plan_hash,schema_version) VALUES (%s,%s,%s,%s,'fixture',1) RETURNING id""",
                    (project["id"], story, revision, jsonb(plan.model_dump(mode="json"))),
                ).fetchone()["id"]
            )
        conn.execute("UPDATE stories SET current_version_id=%s WHERE id=%s", (versions[1], story))
        enqueue(
            conn, project["id"], "render_version", {"version_id": str(versions[0])}, str(uuid4()), "render"
        )
    job = jobs.claim()
    with pytest.raises(ValueError, match="newer version"):
        pipeline.process(job)
    jobs.fail(job, ValueError())
    with connect() as conn:
        assert (
            conn.execute("SELECT current_version_id FROM stories WHERE id=%s", (story,)).fetchone()[
                "current_version_id"
            ]
            == versions[1]
        )
        assert (
            conn.execute("SELECT count(*) n FROM renders WHERE project_id=%s", (project["id"],)).fetchone()[
                "n"
            ]
            == 0
        )
        assert (
            conn.execute(
                "SELECT status FROM storage_objects WHERE project_id=%s AND purpose='render'",
                (project["id"],),
            ).fetchone()["status"]
            == "failed"
        )


def test_cancel_and_missing_objects(client, project):
    prefix = f"/api/projects/{project['id']}"
    with connect() as conn:
        job = enqueue(conn, project["id"], "build_project", {}, str(uuid4()))
    assert client.post(prefix + f"/jobs/{job['id']}/cancel").status_code == 200
    assert jobs.claim() is None
    assert client.post(prefix + f"/jobs/{job['id']}/cancel").status_code == 404
    assert client.get(prefix + f"/objects/{uuid4()}").status_code == 404
    assert client.get(prefix + "/search?q=").status_code == 422
    assert client.get(prefix + "/search?q=test&semantic=true").status_code == 503
    assert client.get("/api/config").status_code == 200
    assert client.get("/livez").status_code == 200
    assert client.delete("/api/session").status_code == 200
    assert client.get("/api/projects").status_code == 401


def test_cleanup_removes_only_unpublished_objects(client, project, videos):
    from vmerger import cleanup, storage

    prefix = f"/api/projects/{project['id']}"
    path = videos[0][0]
    asset = client.post(prefix + "/assets?name=original.mp4", content=path.read_bytes()).json()
    client.post(prefix + "/assets?name=duplicate.mp4", content=path.read_bytes())
    cleanup.main()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM storage_objects WHERE project_id=%s", (project["id"],)).fetchall()
    assert {r["status"] for r in rows} == {"available", "deleted"}
    original = next(r for r in rows if str(r["id"]) == asset["storage_object_id"])
    assert (
        storage.client().head_object(Bucket=original["bucket"], Key=original["object_key"])["ContentLength"]
        > 0
    )


def test_initialization_retries_unready_storage_then_succeeds(database, monkeypatch):
    from vmerger import initialize

    calls = []

    def unavailable_once():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError()

    monkeypatch.setattr(initialize, "ensure_bucket", unavailable_once)
    monkeypatch.setattr(initialize.time, "sleep", lambda _: None)
    initialize.main()
    assert len(calls) == 2
