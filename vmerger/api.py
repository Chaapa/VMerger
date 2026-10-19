import hashlib
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from . import media, storage
from .config import settings
from .contracts import StrictModel, canonical_hash
from .db import connect, enqueue, jsonb

app = FastAPI(title="VMerger", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)


def signer():
    if len(settings().app_token) < 32:
        raise RuntimeError("APP_TOKEN must have at least 32 characters")
    return URLSafeTimedSerializer(settings().app_token, salt="vmerger-session-v1")


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if (
            request.headers.get("origin") != settings().app_origin
            or request.headers.get("x-vmerger-request") != "1"
        ):
            return JSONResponse({"detail": "Invalid request origin"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def owner(request: Request):
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        value = (
            "owner"
            if bearer and secrets.compare_digest(bearer, settings().app_token)
            else signer().loads(request.cookies.get("vmerger_session", ""), max_age=43200)
        )
        if value != "owner":
            raise BadSignature("Unknown subject")
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Sign in to your workspace") from None
    with connect() as conn:
        return conn.execute("""INSERT INTO users(auth_issuer,auth_subject,display_name)
            VALUES ('local','owner','Owner') ON CONFLICT(auth_issuer,auth_subject)
            DO UPDATE SET display_name=users.display_name RETURNING id""").fetchone()["id"]


def project_access(conn, project_id, owner_id, lock=False):
    row = conn.execute(
        "SELECT * FROM projects WHERE id=%s AND owner_id=%s AND status='active'"
        + (" FOR UPDATE" if lock else ""),
        (project_id, owner_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return row


class Login(StrictModel):
    token: str = Field(max_length=512)


@app.post("/api/session")
def login(body: Login, response: Response):
    if not secrets.compare_digest(body.token, settings().app_token):
        raise HTTPException(401, "Invalid workspace key")
    response.set_cookie(
        "vmerger_session",
        signer().dumps("owner"),
        httponly=True,
        secure=settings().cookie_secure,
        samesite="strict",
        max_age=43200,
    )
    return {"ok": True}


@app.delete("/api/session")
def logout(response: Response):
    response.delete_cookie("vmerger_session")
    return {"ok": True}


@app.get("/api/config")
def config(user=Depends(owner)):
    return {
        "ai_available": bool(settings().gemini_api_key),
        "model": settings().gemini_model,
        "max_upload_mb": settings().max_upload_mb,
        "max_asset_seconds": settings().max_asset_seconds,
        "authentication": "single-owner",
    }


class NewProject(StrictModel):
    title: str = Field(min_length=1, max_length=140)
    brief: str = Field(default="", max_length=4000)


@app.get("/api/projects")
def projects(user=Depends(owner)):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM projects WHERE owner_id=%s ORDER BY updated_at DESC", (user,)
        ).fetchall()


@app.post("/api/projects", status_code=201)
def create_project(body: NewProject, user=Depends(owner)):
    with connect() as conn:
        return conn.execute(
            "INSERT INTO projects(owner_id,title,brief) VALUES (%s,%s,%s) RETURNING *",
            (user, body.title, body.brief),
        ).fetchone()


@app.get("/api/projects/{project_id}")
def project(project_id: UUID, user=Depends(owner)):
    with connect() as conn:
        result = dict(project_access(conn, project_id, user))
        for table in ("assets", "stories", "messages", "jobs", "edit_versions", "eval_results"):
            # Table names come exclusively from this constant tuple.
            result[table] = conn.execute(
                f"SELECT * FROM {table} WHERE project_id=%s ORDER BY created_at",  # noqa: S608
                (project_id,),
            ).fetchall()
        result["renders"] = conn.execute(
            """SELECT r.id,r.version_id,r.story_id,r.status,r.duration_us,
            r.storage_object_id FROM renders r WHERE r.project_id=%s ORDER BY created_at""",
            (project_id,),
        ).fetchall()
        result["ai_calls"] = conn.execute(
            """SELECT purpose,model,status,input_tokens,output_tokens,duration_ms,
            estimated_cost_microusd,created_at FROM ai_calls WHERE project_id=%s ORDER BY created_at""",
            (project_id,),
        ).fetchall()
        return result


@app.post("/api/projects/{project_id}/assets", status_code=201)
async def upload(project_id: UUID, request: Request, name: str, license_note: str = "", user=Depends(owner)):
    if not name or len(name) > 240 or len(license_note) > 1000:
        raise HTTPException(422, "Invalid filename or license note")
    object_id = uuid4()
    key = f"projects/{project_id}/originals/{object_id}"
    limit = settings().max_upload_mb * 1024 * 1024
    with connect() as conn:
        project_access(conn, project_id, user, lock=True)
        count = conn.execute(
            "SELECT count(*) n FROM storage_objects WHERE project_id=%s AND purpose='original' AND status IN ('writing','available')",
            (project_id,),
        ).fetchone()["n"]
        if count >= settings().max_project_assets:
            raise HTTPException(409, "Project source limit reached")
        conn.execute(
            """INSERT INTO storage_objects(id,project_id,bucket,object_key,purpose,status,content_type)
            VALUES (%s,%s,%s,%s,'original','writing','application/octet-stream')""",
            (object_id, project_id, settings().s3_bucket, key),
        )
    settings().scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(dir=settings().scratch_dir) as directory:
            path = Path(directory) / "source"
            size = 0
            digest = hashlib.sha256()
            with path.open("wb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "File exceeds upload limit")
                    output.write(chunk)
                    digest.update(chunk)
            if not size:
                raise HTTPException(422, "Empty file")
            info = await run_in_threadpool(media.probe, path)
            if info["kind"] == "audio" and not license_note.strip():
                raise HTTPException(422, "Audio requires a rights/provenance note")
            content_type = "video/mp4" if info["kind"] == "video" else "audio/mpeg"
            verified = await run_in_threadpool(storage.upload_verified, path, key, content_type)
            with connect() as conn:
                project_access(conn, project_id, user, lock=True)
                duplicate = conn.execute(
                    """SELECT a.* FROM assets a JOIN storage_objects o ON o.id=a.storage_object_id
                    WHERE a.project_id=%s AND o.sha256=%s AND o.status='available'""",
                    (project_id, digest.hexdigest()),
                ).fetchone()
                if duplicate:
                    conn.execute("UPDATE storage_objects SET status='failed' WHERE id=%s", (object_id,))
                    # This new key has never been published; the original duplicate stays available.
                    # Cleanup removes the unused key after this transaction commits.
                    return duplicate
                conn.execute(
                    """UPDATE storage_objects SET status='available',byte_size=%s,sha256=%s,
                    etag=%s,verified_at=now(),content_type=%s WHERE id=%s""",
                    (verified["byte_size"], verified["sha256"], verified["etag"], content_type, object_id),
                )
                asset = conn.execute(
                    """INSERT INTO assets(project_id,storage_object_id,kind,original_name,
                    duration_us,width,height,metadata,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'imported') RETURNING *""",
                    (
                        project_id,
                        object_id,
                        info["kind"],
                        name,
                        info["duration_us"],
                        info["width"],
                        info["height"],
                        jsonb(
                            {
                                "has_audio": info["has_audio"],
                                "license_confirmed": bool(license_note.strip()),
                                "license_note": license_note,
                            }
                        ),
                    ),
                ).fetchone()
                if info["kind"] == "audio":
                    conn.execute("UPDATE assets SET status='ready' WHERE id=%s", (asset["id"],))
                elif settings().gemini_api_key:
                    enqueue(
                        conn, project_id, "analyze_asset", {"asset_id": str(asset["id"])}, str(asset["id"])
                    )
                return asset
    except HTTPException:
        with connect() as conn:
            conn.execute(
                "UPDATE storage_objects SET status='failed' WHERE id=%s AND status='writing'", (object_id,)
            )
        raise
    except ValueError as error:
        with connect() as conn:
            conn.execute(
                "UPDATE storage_objects SET status='failed' WHERE id=%s AND status='writing'", (object_id,)
            )
        raise HTTPException(422, str(error)) from None
    except Exception:
        with connect() as conn:
            conn.execute(
                "UPDATE storage_objects SET status='failed' WHERE id=%s AND status='writing'", (object_id,)
            )
        raise HTTPException(503, "Upload could not be completed") from None


class ChatMessage(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    request_id: UUID
    story_id: UUID | None = None
    context_version_id: UUID | None = None


@app.post("/api/projects/{project_id}/messages", status_code=202)
def message(project_id: UUID, body: ChatMessage, user=Depends(owner)):
    if not settings().gemini_api_key:
        raise HTTPException(503, "Add GEMINI_API_KEY to .env and restart API and worker to enable AI")
    fingerprint = canonical_hash(body.model_dump(mode="json"))
    with connect() as conn:
        project_access(conn, project_id, user, lock=True)
        existing = conn.execute(
            "SELECT * FROM messages WHERE project_id=%s AND request_id=%s", (project_id, body.request_id)
        ).fetchone()
        if existing:
            if existing["request_fingerprint"] != fingerprint:
                raise HTTPException(409, "Request ID already used for a different command")
            return existing
        if conn.execute(
            "SELECT 1 FROM jobs WHERE project_id=%s AND status IN ('queued','running')", (project_id,)
        ).fetchone():
            raise HTTPException(409, "Wait for the current operation or cancel it")
        unready = conn.execute(
            "SELECT 1 FROM assets WHERE project_id=%s AND kind='video' AND status<>'ready'", (project_id,)
        ).fetchone()
        videos = conn.execute(
            "SELECT 1 FROM assets WHERE project_id=%s AND kind='video'", (project_id,)
        ).fetchone()
        if unready or not videos:
            raise HTTPException(409, "Upload videos and run analysis before creating a story")
        if body.story_id:
            story = conn.execute(
                "SELECT * FROM stories WHERE project_id=%s AND id=%s", (project_id, body.story_id)
            ).fetchone()
            if not story or story["current_version_id"] != body.context_version_id:
                raise HTTPException(409, "Story version changed; refresh before submitting")
        elif body.context_version_id:
            raise HTTPException(422, "Version context requires a story")
        row = conn.execute(
            """INSERT INTO messages(project_id,story_id,context_version_id,author_id,role,text,
            request_id,request_fingerprint) VALUES (%s,%s,%s,%s,'user',%s,%s,%s) RETURNING *""",
            (
                project_id,
                body.story_id,
                body.context_version_id,
                user,
                body.text,
                body.request_id,
                fingerprint,
            ),
        ).fetchone()
        enqueue(conn, project_id, "apply_message", {"message_id": str(row["id"])}, str(row["id"]))
        return row


@app.post("/api/projects/{project_id}/analyze", status_code=202)
def analyze_pending(project_id: UUID, user=Depends(owner)):
    if not settings().gemini_api_key:
        raise HTTPException(503, "Gemini is not configured")
    with connect() as conn:
        project_access(conn, project_id, user, lock=True)
        assets = conn.execute(
            "SELECT id FROM assets WHERE project_id=%s AND kind='video' AND status<>'ready'", (project_id,)
        ).fetchall()
        for asset in assets:
            enqueue(conn, project_id, "analyze_asset", {"asset_id": str(asset["id"])}, str(uuid4()))
        return {"queued": len(assets)}


@app.post("/api/projects/{project_id}/jobs/{job_id}/cancel")
def cancel(project_id: UUID, job_id: UUID, user=Depends(owner)):
    with connect() as conn:
        project_access(conn, project_id, user, lock=True)
        row = conn.execute(
            """UPDATE jobs SET cancel_requested=true WHERE project_id=%s AND id=%s
            AND status IN ('queued','running') RETURNING id""",
            (project_id, job_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Active job not found")
        return {"ok": True}


@app.get("/api/projects/{project_id}/objects/{object_id}")
def media_stream(project_id: UUID, object_id: UUID, request: Request, user=Depends(owner)):
    with connect() as conn:
        project_access(conn, project_id, user)
        row = conn.execute(
            "SELECT * FROM storage_objects WHERE project_id=%s AND id=%s AND status='available'",
            (project_id, object_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Media not found")
    kwargs = {"Bucket": row["bucket"], "Key": row["object_key"]}
    byte_range = request.headers.get("range")
    if byte_range:
        import re

        if not re.fullmatch(r"bytes=(\d+-\d*|-\d+)", byte_range):
            raise HTTPException(416, "Unsupported byte range")
        kwargs["Range"] = byte_range
    try:
        obj = storage.client().get_object(**kwargs)
    except Exception:
        raise HTTPException(416 if byte_range else 503, "Media unavailable") from None

    def chunks():
        with obj["Body"] as stream:
            yield from iter(lambda: stream.read(256 * 1024), b"")

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(obj["ContentLength"])}
    if "ContentRange" in obj:
        headers["Content-Range"] = obj["ContentRange"]
    return StreamingResponse(
        chunks(), status_code=206 if byte_range else 200, media_type=row["content_type"], headers=headers
    )


@app.get("/api/projects/{project_id}/search")
def search(project_id: UUID, q: str, semantic: bool = False, user=Depends(owner)):
    if not 1 <= len(q) <= 1000:
        raise HTTPException(422, "Search must contain 1–1000 characters")
    with connect() as conn:
        project_access(conn, project_id, user)
    if semantic:
        if not settings().gemini_api_key:
            raise HTTPException(503, "Gemini is not configured")
        from .providers import Gemini

        vector = Gemini(None).embed([q], query=True)[0]
        with connect() as conn:
            project_access(conn, project_id, user)
            return conn.execute(
                """WITH scoped AS MATERIALIZED (
                SELECT e.segment_id,e.embedding FROM segment_embeddings e
                WHERE e.project_id=%s AND e.profile_key=%s)
                SELECT s.id,s.asset_id,s.start_us,s.end_us,s.description,
                1-(e.embedding <=> %s::vector) score FROM scoped e JOIN segments s ON s.id=e.segment_id
                ORDER BY e.embedding <=> %s::vector,s.id LIMIT 30""",
                (project_id, settings().embedding_profile, str(vector), str(vector)),
            ).fetchall()
    with connect() as conn:
        return conn.execute(
            """SELECT id,asset_id,start_us,end_us,description,
            ts_rank_cd(search_vector,plainto_tsquery('simple',%s)) score
            FROM segments WHERE project_id=%s AND search_vector@@plainto_tsquery('simple',%s)
            ORDER BY score DESC,id LIMIT 30""",
            (q, project_id, q),
        ).fetchall()


@app.get("/livez")
def live():
    return {"status": "alive"}


@app.get("/readyz")
def ready():
    try:
        with connect() as conn:
            conn.execute("SELECT 1 FROM alembic_version").fetchone()
        storage.client().head_bucket(Bucket=settings().s3_bucket)
        return {"status": "ready", "ai_available": bool(settings().gemini_api_key)}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)


@app.get("/api/metrics")
def metrics(user=Depends(owner)):
    from .monitoring import exposition

    return Response(exposition(user), media_type="text/plain; version=0.0.4")


web = Path(__file__).resolve().parents[1] / "web" / "dist"
if web.exists():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
