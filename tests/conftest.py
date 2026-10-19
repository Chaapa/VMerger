import os
from uuid import uuid4

import pytest


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", help="Use real PostgreSQL, S3 and FFmpeg")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Pass --integration with running services"))


@pytest.fixture(scope="session")
def database(request):
    if not request.config.getoption("--integration"):
        pytest.skip("Integration services not requested")
    import psycopg
    from alembic import command
    from alembic.config import Config
    from psycopg import sql

    from vmerger import storage
    from vmerger.config import settings
    from vmerger.db import connect

    original = settings().database_url
    schema = "test_" + uuid4().hex
    with psycopg.connect(original, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    # Isolate all tests from the user's application tables without resetting their database.
    os.environ["DATABASE_URL"] = (
        original + ("&" if "?" in original else "?") + "options=-csearch_path%3D" + schema + ",public"
    )
    os.environ["DATABASE_SCHEMA"] = schema
    settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    with connect() as conn:
        assert conn.execute("SELECT current_schema() s").fetchone()["s"] == schema
        assert conn.execute("SELECT count(*) n FROM projects").fetchone()["n"] == 0
    storage.ensure_bucket()
    yield
    with connect() as conn:
        keys = conn.execute("SELECT object_key FROM storage_objects").fetchall()
    for key in keys:
        storage.delete(key["object_key"])
    with psycopg.connect(original, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("DATABASE_SCHEMA", None)
    settings.cache_clear()


@pytest.fixture
def client(database):
    from fastapi.testclient import TestClient

    from vmerger.api import app
    from vmerger.config import settings

    with TestClient(app, headers={"Origin": settings().app_origin, "X-VMerger-Request": "1"}) as client:
        assert client.post("/api/session", json={"token": settings().app_token}).status_code == 200
        yield client


@pytest.fixture
def project(client):
    return client.post(
        "/api/projects", json={"title": "Automated integration fixture", "brief": "Test-only media"}
    ).json()


@pytest.fixture(scope="session")
def videos(database, tmp_path_factory):
    from vmerger.media import command, run

    root = tmp_path_factory.mktemp("media-fixtures")
    paths = []
    for color, audio in [("teal", False), ("orange", True)]:
        path = root / f"{color}.mp4"
        args = command() + ["-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=30:d=2"]
        if audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac"]
        run(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "2", str(path)])
        paths.append(path)
    music = root / "music.wav"
    run(command() + ["-f", "lavfi", "-i", "sine=frequency=220:duration=3", str(music)])
    return paths, music
