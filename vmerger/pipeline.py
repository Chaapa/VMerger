from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from . import jobs, media, storage
from .config import settings
from .contracts import MusicChoice, ProjectPlan, Review, StoryPlan, canonical_hash, validate_plan
from .db import connect, enqueue, jsonb
from .providers import ProviderRouter, context_json


def assets_for(project_id):
    with connect() as conn:
        rows = conn.execute(
            """SELECT a.*,o.object_key FROM assets a JOIN storage_objects o
            ON o.id=a.storage_object_id WHERE a.project_id=%s AND o.status='available'""",
            (project_id,),
        ).fetchall()
        return {str(x["id"]): x for x in rows}


def analyze(job, provider):
    assets = assets_for(job["project_id"])
    asset = assets[job["input"]["asset_id"]]
    duration = asset["duration_us"] / 1_000_000
    with TemporaryDirectory(dir=settings().scratch_dir) as directory:
        source, proxy = Path(directory) / "source", Path(directory) / "proxy.mp4"
        storage.download(asset["object_key"], source)
        media.proxy(source, proxy)
        analysis = provider.analyze(proxy, duration)
        for scene in analysis.scenes:
            if scene.end > duration + 0.001:
                raise ValueError("Analysis scene exceeds source duration")
        vectors = provider.embed([s.description + " " + s.speech for s in analysis.scenes])
        if len(vectors) != len(analysis.scenes):
            raise ValueError("Provider returned incomplete embeddings")
    fingerprint = canonical_hash({"route": provider.describe("analyst"), "analysis": analysis.model_dump()})
    with connect() as conn:
        jobs.fence(conn, job)
        # An already analyzed source is immutable; duplicate analyze jobs do not duplicate scenes.
        current = conn.execute("SELECT status FROM assets WHERE id=%s FOR UPDATE", (asset["id"],)).fetchone()
        if current["status"] == "ready":
            jobs.succeed(conn, job)
            return
        for scene, vector in zip(analysis.scenes, vectors, strict=True):
            text = scene.description + " " + scene.speech
            segment = conn.execute(
                """INSERT INTO segments(project_id,asset_id,start_us,end_us,description,
                search_text,analysis_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    job["project_id"],
                    asset["id"],
                    round(scene.start * 1e6),
                    round(scene.end * 1e6),
                    scene.description,
                    text,
                    fingerprint,
                ),
            ).fetchone()["id"]
            conn.execute(
                """INSERT INTO segment_embeddings(project_id,segment_id,profile_key,provider,model,
                content_sha256,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s::vector)""",
                (
                    job["project_id"],
                    segment,
                    provider.embedding_profile,
                    provider.describe("embedding")["provider"],
                    provider.describe("embedding")["model"],
                    canonical_hash(text),
                    str(vector),
                ),
            )
            if scene.speech:
                conn.execute(
                    """INSERT INTO transcript_spans(project_id,asset_id,start_us,end_us,text,
                    analysis_fingerprint) VALUES (%s,%s,%s,%s,%s,%s)""",
                    (
                        job["project_id"],
                        asset["id"],
                        round(scene.start * 1e6),
                        round(scene.end * 1e6),
                        scene.speech,
                        fingerprint,
                    ),
                )
        conn.execute("UPDATE assets SET status='ready' WHERE id=%s", (asset["id"],))
        jobs.succeed(conn, job)
    jobs.observe(job, "analyst", "source_bounds_pass", 1, len(analysis.scenes), len(analysis.scenes))


def plan(job, provider):
    assets = assets_for(job["project_id"])
    with connect() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=%s", (job["project_id"],)).fetchone()
        message = conn.execute(
            "SELECT * FROM messages WHERE id=%s AND project_id=%s",
            (job["input"]["message_id"], job["project_id"]),
        ).fetchone()
        scenes = conn.execute(
            """SELECT asset_id,start_us,end_us,description,search_text FROM segments
            WHERE project_id=%s ORDER BY asset_id,start_us LIMIT 301""",
            (job["project_id"],),
        ).fetchall()
        previous = None
        if message["context_version_id"]:
            previous = conn.execute(
                "SELECT plan FROM edit_versions WHERE id=%s", (message["context_version_id"],)
            ).fetchone()["plan"]
    if len(scenes) > 300:
        raise ValueError("Scene context budget exceeded; split this project")
    context = {
        "brief": project["brief"],
        "request": message["text"],
        "previous_plan": previous,
        "scenes": scenes,
        "source_durations": {k: v["duration_us"] / 1e6 for k, v in assets.items()},
        "max_output_seconds": settings().max_output_seconds,
    }
    instruction = "Design coherent stories from these observed scenes. Use source seconds, not microseconds. "
    instruction += (
        "Return exactly one revised story." if previous else "Group related events into one or more stories."
    )
    proposal = provider.call("director", instruction + context_json(context), ProjectPlan)
    if previous and len(proposal.stories) != 1:
        raise ValueError("A story revision must produce exactly one story")
    library = [
        {"id": k, "name": v["original_name"], "rights": v["metadata"].get("license_note")}
        for k, v in assets.items()
        if v["kind"] == "audio" and v["metadata"].get("license_confirmed")
    ]
    plans = []
    for story_number, candidate in enumerate(proposal.stories, start=1):
        choice = provider.call(
            "music",
            "Select suitable music ONLY from this licensed project library. "
            "Return null when no appropriate track exists. Respect requests for no music. "
            + context_json(
                {"request": message["text"], "story": candidate.model_dump(mode="json"), "library": library}
            ),
            MusicChoice,
        )
        candidate.music_asset_id = choice.music_asset_id
        edited = provider.call(
            "editor",
            "Refine the rhythm and choose effects from none, warm, monochrome, fade. "
            "Preserve the music choice, source IDs, factual events and user constraints. Return the complete plan. "
            + context_json({"request": message["text"], "plan": candidate.model_dump(mode="json")}),
            StoryPlan,
        )
        # Music authorization is owned by the music role and deterministic validator.
        edited.music_asset_id = choice.music_asset_id
        try:
            validate_plan(edited, assets, settings().max_output_seconds)
            jobs.observe(job, "editor", "plan_valid", 1, story_number, story_number)
        except ValueError:
            jobs.observe(
                job, "editor", "plan_valid", (story_number - 1) / story_number, story_number - 1, story_number
            )
            raise
        review = provider.call(
            "reviewer",
            "Review source support, requested changes, pacing and music choice. "
            "Reject invented events or violations. This is a quality judgment, not a security check. "
            + context_json(
                {"request": message["text"], "scenes": scenes, "plan": edited.model_dump(mode="json")}
            ),
            Review,
        )
        jobs.observe(
            job,
            "reviewer",
            "provider_approval",
            (story_number - 1 + int(review.approved)) / story_number,
            story_number - 1 + int(review.approved),
            story_number,
            source="provider",
            details={"issues": review.issues},
        )
        if not review.approved:
            raise ValueError("Reviewer rejected the plan; ask for a revised brief")
        plans.append(edited)
    with connect() as conn:
        jobs.fence(conn, job)
        for edited in plans:
            if message["story_id"]:
                story_id = message["story_id"]
                story = conn.execute("SELECT * FROM stories WHERE id=%s FOR UPDATE", (story_id,)).fetchone()
                if story["current_version_id"] != message["context_version_id"]:
                    raise ValueError("Stale story revision")
                revision = conn.execute(
                    "SELECT coalesce(max(revision),0)+1 n FROM edit_versions WHERE story_id=%s", (story_id,)
                ).fetchone()["n"]
            else:
                story_id = conn.execute(
                    """INSERT INTO stories(project_id,title,description,status)
                    VALUES (%s,%s,%s,'rendering') RETURNING id""",
                    (job["project_id"], edited.title, edited.summary),
                ).fetchone()["id"]
                revision = 1
            serialized = edited.model_dump(mode="json")
            version = conn.execute(
                """INSERT INTO edit_versions(project_id,story_id,revision,parent_version_id,
                source_message_id,plan,plan_hash,schema_version,change_summary)
                VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s) RETURNING id""",
                (
                    job["project_id"],
                    story_id,
                    revision,
                    message["context_version_id"],
                    message["id"],
                    jsonb(serialized),
                    canonical_hash(serialized),
                    edited.summary,
                ),
            ).fetchone()["id"]
            conn.execute("UPDATE stories SET status='rendering' WHERE id=%s", (story_id,))
            enqueue(
                conn,
                job["project_id"],
                "render_version",
                {"version_id": str(version)},
                str(version),
                "render",
            )
        conn.execute(
            "INSERT INTO messages(project_id,story_id,role,text) VALUES (%s,%s,'assistant',%s)",
            (job["project_id"], message["story_id"], f"Plan ready. Rendering {len(plans)} stories."),
        )
        jobs.succeed(conn, job)


def render_version(job):
    assets = assets_for(job["project_id"])
    with connect() as conn:
        version = conn.execute(
            "SELECT * FROM edit_versions WHERE id=%s AND project_id=%s",
            (job["input"]["version_id"], job["project_id"]),
        ).fetchone()
        if not version:
            raise ValueError("Version not found")
    plan = StoryPlan.model_validate(version["plan"])
    expected = validate_plan(plan, assets, settings().max_output_seconds)
    object_id = uuid4()
    key = f"projects/{job['project_id']}/renders/{object_id}.mp4"
    with connect() as conn:
        jobs.fence(conn, job)
        conn.execute(
            """INSERT INTO storage_objects(id,project_id,bucket,object_key,purpose,status,content_type)
            VALUES (%s,%s,%s,%s,'render','writing','video/mp4')""",
            (object_id, job["project_id"], settings().s3_bucket, key),
        )
    try:
        with TemporaryDirectory(dir=settings().scratch_dir) as directory:
            root = Path(directory)
            ids = {str(c.asset_id) for c in plan.clips}
            if plan.music_asset_id:
                ids.add(str(plan.music_asset_id))
            paths = {}
            for asset_id in ids:
                paths[asset_id] = root / asset_id
                storage.download(assets[asset_id]["object_key"], paths[asset_id])
            output, duration = media.render(plan, paths, assets, root)
            verified = storage.upload_verified(output, key, "video/mp4")
        with connect() as conn:
            jobs.fence(conn, job)
            story = conn.execute(
                "SELECT current_version_id FROM stories WHERE id=%s FOR UPDATE", (version["story_id"],)
            ).fetchone()
            if story["current_version_id"] != version["parent_version_id"]:
                raise ValueError("A newer version already exists; stale render cannot become current")
            conn.execute(
                """UPDATE storage_objects SET status='available',byte_size=%s,sha256=%s,etag=%s,
                verified_at=now() WHERE id=%s""",
                (verified["byte_size"], verified["sha256"], verified["etag"], object_id),
            )
            conn.execute(
                """INSERT INTO renders(project_id,story_id,version_id,job_id,purpose,profile,profile_hash,
                status,storage_object_id,duration_us,completed_at)
                VALUES (%s,%s,%s,%s,'export',%s,'720p-v1','ready',%s,%s,now())""",
                (
                    job["project_id"],
                    version["story_id"],
                    version["id"],
                    job["id"],
                    jsonb({"height": 720, "fps": 30}),
                    object_id,
                    round(duration * 1e6),
                ),
            )
            conn.execute(
                """UPDATE stories SET current_version_id=%s,status='ready',title=%s,description=%s,
                updated_at=now() WHERE id=%s""",
                (version["id"], plan.title, plan.summary, version["story_id"]),
            )
            conn.execute(
                "INSERT INTO messages(project_id,story_id,role,text) VALUES (%s,%s,'assistant',%s)",
                (
                    job["project_id"],
                    version["story_id"],
                    f"Ready: “{plan.title}”, version {version['revision']}.",
                ),
            )
            jobs.succeed(conn, job)
        jobs.observe(job, "renderer", "decode_pass", 1, 1, 1)
        jobs.observe(job, "renderer", "duration_error_seconds", abs(duration - expected))
    except Exception:
        with connect() as conn:
            conn.execute(
                "UPDATE storage_objects SET status='failed' WHERE id=%s AND status='writing'", (object_id,)
            )
        raise


def reindex_embeddings(job, provider):
    profile = provider.embedding_profile
    if job["input"]["profile"] != profile:
        raise ValueError("Embedding configuration changed; request reindexing again")
    while True:
        with connect() as conn:
            jobs.fence(conn, job)
            rows = conn.execute(
                """SELECT s.id,s.search_text FROM segments s
                LEFT JOIN segment_embeddings e ON e.segment_id=s.id AND e.profile_key=%s
                WHERE s.project_id=%s AND e.segment_id IS NULL ORDER BY s.id LIMIT 32""",
                (profile, job["project_id"]),
            ).fetchall()
        if not rows:
            break
        vectors = provider.embed([row["search_text"] for row in rows])
        if len(vectors) != len(rows):
            raise ValueError("Provider returned incomplete embeddings")
        with connect() as conn:
            jobs.fence(conn, job)
            for row, vector in zip(rows, vectors, strict=True):
                conn.execute(
                    """INSERT INTO segment_embeddings(project_id,segment_id,profile_key,provider,model,
                    content_sha256,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT(segment_id,profile_key) DO NOTHING""",
                    (job["project_id"], row["id"], profile, provider.describe("embedding")["provider"],
                     provider.describe("embedding")["model"], canonical_hash(row["search_text"]), str(vector)),
                )
    with connect() as conn:
        jobs.fence(conn, job)
        jobs.succeed(conn, job)


def process(job, provider_factory=ProviderRouter):
    settings().scratch_dir.mkdir(parents=True, exist_ok=True)
    with jobs.keep_alive(job):
        if job["kind"] == "analyze_asset":
            analyze(job, provider_factory(job))
        elif job["kind"] in {"apply_message", "build_project"}:
            plan(job, provider_factory(job))
        elif job["kind"] == "render_version":
            render_version(job)
        elif job["kind"] == "reindex_embeddings":
            reindex_embeddings(job, provider_factory(job))
        else:
            raise ValueError("Unsupported job kind")
