"""Remove failed, unpublished S3 objects. Never delete available or in-flight media."""

from . import storage
from .db import connect


def main():
    with connect() as conn:
        rows = conn.execute("""SELECT o.id,o.object_key FROM storage_objects o
            WHERE o.status='failed' AND NOT EXISTS (SELECT 1 FROM assets a WHERE a.storage_object_id=o.id)
            AND NOT EXISTS (SELECT 1 FROM renders r WHERE r.storage_object_id=o.id)
            AND NOT EXISTS (SELECT 1 FROM derivatives d WHERE d.storage_object_id=o.id)""").fetchall()
    for row in rows:
        storage.delete(row["object_key"])
        with connect() as conn:
            conn.execute(
                "UPDATE storage_objects SET status='deleted',updated_at=now() WHERE id=%s AND status='failed'",
                (row["id"],),
            )
    print(f"Removed {len(rows)} failed, unpublished objects")


if __name__ == "__main__":
    main()
