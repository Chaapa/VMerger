FROM node:22-bookworm-slim AS web
WORKDIR /web
RUN npm install -g pnpm@11.25.0
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm run build

FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.licenses="MIT"
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock pyproject.toml LICENSE ./
RUN pip install --no-cache-dir -r requirements.lock
COPY vmerger/ vmerger/
COPY migrations/ migrations/
COPY docs/schema.sql docs/schema.sql
COPY alembic.ini ./
COPY config/ config/
COPY --from=web /web/dist web/dist
RUN useradd --uid 10001 --create-home vmerger
USER vmerger
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "vmerger.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
