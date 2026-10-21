import time

from alembic import command
from alembic.config import Config

from .storage import ensure_bucket


def main():
    command.upgrade(Config("alembic.ini"), "head")
    for attempt in range(30):
        try:
            ensure_bucket()
            print("Database and private S3 bucket ready")
            return
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)


if __name__ == "__main__":
    main()
