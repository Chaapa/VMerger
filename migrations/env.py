from alembic import context
from sqlalchemy import create_engine, pool

from vmerger.config import settings

engine = create_engine(
    settings().database_url.replace("postgresql://", "postgresql+psycopg://"), poolclass=pool.NullPool
)
with engine.connect() as conn:
    context.configure(connection=conn, version_table_schema=settings().database_schema)
    with context.begin_transaction():
        context.run_migrations()
