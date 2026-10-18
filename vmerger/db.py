from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import settings


@contextmanager
def connect():
    # Short-lived connections keep worker network/FFmpeg work outside transactions.
    with psycopg.connect(settings().database_url, row_factory=dict_row, connect_timeout=5) as conn:
        yield conn


def jsonb(value):
    return Jsonb(value)


def enqueue(conn, project_id, kind, payload, dedupe_key, queue="ai"):
    return conn.execute(
        """INSERT INTO jobs(project_id,queue,kind,input,dedupe_key)
           VALUES (%s,%s,%s,%s,%s) ON CONFLICT(project_id,kind,dedupe_key)
           DO UPDATE SET dedupe_key=excluded.dedupe_key RETURNING *""",
        (project_id, queue, kind, jsonb(payload), dedupe_key),
    ).fetchone()
