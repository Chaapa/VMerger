-- VMerger: initial PostgreSQL + pgvector schema for an EMPTY database.
-- Target PostgreSQL 18, pgvector >= 0.8.0. Not a SQLite migration.
-- Run as a migration role. API/worker roles must not own tables or run DDL.
-- Media stays in private S3. Credentials stay in server configuration.
-- Media ranges: BIGINT microseconds [start, end); dates: timestamptz.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_issuer text NOT NULL,
    auth_subject text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (auth_issuer, auth_subject)
);

CREATE TABLE projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id),
    title text NOT NULL,
    brief text NOT NULL DEFAULT '',
    settings jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(settings) = 'object'),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleting')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX projects_owner_updated ON projects(owner_id, updated_at DESC, id);

-- Single source of checksums/sizes; storage_backend resolves to deployment config.
CREATE TABLE storage_objects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    storage_backend text NOT NULL DEFAULT 'nas',
    bucket text NOT NULL,
    object_key text NOT NULL CHECK (length(object_key) > 0),
    purpose text NOT NULL CHECK (purpose IN ('original', 'derived', 'render')),
    status text NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'writing', 'available', 'failed', 'deleting', 'deleted')),
    content_type text NOT NULL,
    byte_size bigint CHECK (byte_size IS NULL OR byte_size > 0),
    sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    etag text,
    verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    UNIQUE (storage_backend, bucket, object_key),
    CHECK (status <> 'available' OR
        (byte_size IS NOT NULL AND sha256 IS NOT NULL AND verified_at IS NOT NULL))
);
CREATE INDEX objects_cleanup ON storage_objects(status, updated_at);
CREATE UNIQUE INDEX originals_dedup ON storage_objects(project_id, sha256)
    WHERE purpose = 'original' AND status = 'available';

CREATE TABLE assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    storage_object_id uuid NOT NULL UNIQUE,
    kind text NOT NULL CHECK (kind IN ('video', 'audio', 'image')),
    original_name text NOT NULL,
    duration_us bigint CHECK (duration_us IS NULL OR duration_us > 0),
    width integer CHECK (width IS NULL OR width > 0),
    height integer CHECK (height IS NULL OR height > 0),
    fps_num integer CHECK (fps_num IS NULL OR fps_num > 0),
    fps_den integer CHECK (fps_den IS NULL OR fps_den > 0),
    captured_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'imported'
        CHECK (status IN ('imported', 'processing', 'ready', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    FOREIGN KEY (project_id, storage_object_id) REFERENCES storage_objects(project_id, id) DEFERRABLE INITIALLY DEFERRED
);

-- S3 ListParts is authoritative; no duplicate upload_parts ledger.
CREATE TABLE upload_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    storage_object_id uuid NOT NULL UNIQUE,
    request_id uuid NOT NULL,
    request_fingerprint text NOT NULL,
    original_name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('video', 'audio', 'image')),
    expected_byte_size bigint NOT NULL CHECK (expected_byte_size > 0),
    expected_sha256 text CHECK (expected_sha256 IS NULL OR expected_sha256 ~ '^[0-9a-f]{64}$'),
    source_fingerprint text NOT NULL,
    multipart_upload_id text,
    part_size bigint NOT NULL CHECK (part_size BETWEEN 5242880 AND 5368709120),
    status text NOT NULL DEFAULT 'initiating'
        CHECK (status IN ('initiating', 'uploading', 'verifying', 'completed', 'aborted', 'failed')),
    result_asset_id uuid,
    expires_at timestamptz NOT NULL,
    write_urls_expire_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (project_id, request_id),
    CHECK (status NOT IN ('uploading', 'verifying', 'completed') OR multipart_upload_id IS NOT NULL),
    CHECK (status <> 'completed' OR (result_asset_id IS NOT NULL AND completed_at IS NOT NULL)),
    FOREIGN KEY (project_id, storage_object_id) REFERENCES storage_objects(project_id, id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (project_id, result_asset_id) REFERENCES assets(project_id, id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX uploads_expiry ON upload_sessions(status, expires_at);

CREATE TABLE derivatives (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    storage_object_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('proxy', 'audio', 'thumbnail', 'chunk')),
    profile_hash text NOT NULL,
    duration_us bigint CHECK (duration_us IS NULL OR duration_us > 0),
    source_start_us bigint NOT NULL DEFAULT 0 CHECK (source_start_us >= 0),
    mapping jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    UNIQUE (asset_id, kind, profile_hash),
    FOREIGN KEY (project_id, asset_id) REFERENCES assets(project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, storage_object_id) REFERENCES storage_objects(project_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    start_us bigint NOT NULL CHECK (start_us >= 0),
    end_us bigint NOT NULL CHECK (end_us > start_us),
    description text NOT NULL,
    search_text text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS
        (to_tsvector('simple'::regconfig, search_text)) STORED,
    annotations jsonb NOT NULL DEFAULT '{}',
    analysis_fingerprint text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    UNIQUE (asset_id, analysis_fingerprint, start_us, end_us),
    FOREIGN KEY (project_id, asset_id) REFERENCES assets(project_id, id) ON DELETE CASCADE
);
CREATE INDEX segments_project_asset_time ON segments(project_id, asset_id, start_us);
CREATE INDEX segments_fts ON segments USING gin(search_vector);

CREATE TABLE transcript_spans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    start_us bigint NOT NULL CHECK (start_us >= 0),
    end_us bigint NOT NULL CHECK (end_us > start_us),
    text text NOT NULL,
    language text,
    speaker_label text,
    words jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(words) = 'array'),
    analysis_fingerprint text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, analysis_fingerprint, start_us, end_us),
    FOREIGN KEY (project_id, asset_id) REFERENCES assets(project_id, id) ON DELETE CASCADE
);
CREATE INDEX transcript_project_asset_time ON transcript_spans(project_id, asset_id, start_us);

CREATE TABLE stories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title text NOT NULL,
    description text NOT NULL DEFAULT '',
    cover_derivative_id uuid,
    current_version_id uuid,
    status text NOT NULL DEFAULT 'planning'
        CHECK (status IN ('planning', 'rendering', 'ready', 'failed', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    FOREIGN KEY (project_id, cover_derivative_id) REFERENCES derivatives(project_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE edit_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    story_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    parent_version_id uuid,
    source_message_id uuid,
    plan jsonb NOT NULL CHECK (jsonb_typeof(plan) = 'object'),
    constraints jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(constraints) = 'object'),
    plan_hash text NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    change_summary text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, story_id, id),
    UNIQUE (story_id, revision),
    CHECK (parent_version_id IS NULL OR parent_version_id <> id),
    FOREIGN KEY (project_id, story_id) REFERENCES stories(project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, story_id, parent_version_id) REFERENCES edit_versions(project_id, story_id, id) DEFERRABLE INITIALLY DEFERRED
);
ALTER TABLE stories ADD CONSTRAINT stories_current_version_fk
    FOREIGN KEY (project_id, id, current_version_id)
    REFERENCES edit_versions(project_id, story_id, id) DEFERRABLE INITIALLY DEFERRED;

-- Only domain trigger: editing snapshots cannot be modified in place.
CREATE FUNCTION reject_edit_version_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Edit versions are immutable; create a new version';
END;
$$;
CREATE TRIGGER edit_versions_immutable BEFORE UPDATE ON edit_versions
    FOR EACH ROW EXECUTE FUNCTION reject_edit_version_update();

CREATE TABLE messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    story_id uuid,
    context_version_id uuid,
    author_id uuid REFERENCES users(id),
    playback_us bigint CHECK (playback_us IS NULL OR playback_us >= 0),
    role text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    text text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    request_id uuid,
    request_fingerprint text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    UNIQUE (project_id, request_id),
    CHECK (role <> 'user' OR (author_id IS NOT NULL AND request_id IS NOT NULL)),
    CHECK (request_id IS NULL OR request_fingerprint IS NOT NULL),
    CHECK (context_version_id IS NULL OR story_id IS NOT NULL),
    CHECK (playback_us IS NULL OR context_version_id IS NOT NULL),
    FOREIGN KEY (project_id, story_id) REFERENCES stories(project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, story_id, context_version_id) REFERENCES edit_versions(project_id, story_id, id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX messages_scope_time ON messages(project_id, story_id, created_at, id);
ALTER TABLE edit_versions ADD CONSTRAINT versions_source_message_fk
    FOREIGN KEY (project_id, source_message_id) REFERENCES messages(project_id, id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE segment_embeddings (
    project_id uuid NOT NULL,
    segment_id uuid NOT NULL,
    profile_key text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    embedding vector(768) NOT NULL CHECK (abs(vector_norm(embedding) - 1) < 0.001),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (segment_id, profile_key),
    FOREIGN KEY (project_id, segment_id) REFERENCES segments(project_id, id) ON DELETE CASCADE
);
CREATE INDEX embeddings_project_profile ON segment_embeddings(project_id, profile_key);
-- Incompatible profiles need separate indexes. Dimension changes require a migration.
CREATE INDEX embeddings_text_v1_hnsw ON segment_embeddings USING hnsw(embedding vector_cosine_ops)
    WHERE profile_key = 'gemini-embedding-001:text-v1:768';

-- Same codebase, independently scalable I/O, AI and render workers.
CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    queue text NOT NULL CHECK (queue IN ('io', 'ai', 'render')),
    kind text NOT NULL CHECK (kind IN ('verify_upload', 'analyze_asset', 'build_project',
        'apply_message', 'render_version', 'reconcile_storage', 'delete_project')),
    input jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(input) = 'object'),
    checkpoint jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(checkpoint) = 'object'),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    progress real NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    dedupe_key text NOT NULL,
    locked_by text,
    lease_token uuid,
    lease_expires_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    error jsonb,
    available_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    UNIQUE (project_id, kind, dedupe_key),
    CHECK (attempt <= max_attempts),
    CHECK ((status = 'running') =
        (locked_by IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CHECK (status = 'running' OR
        (locked_by IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL))
);
CREATE INDEX jobs_claim ON jobs(queue, available_at, created_at, id) WHERE status = 'queued';
CREATE INDEX jobs_expired ON jobs(lease_expires_at) WHERE status = 'running';
CREATE INDEX jobs_project ON jobs(project_id, status, created_at);

CREATE TABLE renders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    story_id uuid NOT NULL,
    version_id uuid NOT NULL,
    job_id uuid,
    purpose text NOT NULL CHECK (purpose IN ('preview', 'export')),
    profile jsonb NOT NULL CHECK (jsonb_typeof(profile) = 'object'),
    profile_hash text NOT NULL,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'rendering', 'ready', 'failed', 'cancelled')),
    storage_object_id uuid,
    duration_us bigint CHECK (duration_us IS NULL OR duration_us > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (version_id, purpose, profile_hash),
    CHECK (status <> 'ready' OR
        (storage_object_id IS NOT NULL AND duration_us IS NOT NULL AND completed_at IS NOT NULL)),
    FOREIGN KEY (project_id, story_id, version_id) REFERENCES edit_versions(project_id, story_id, id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, job_id) REFERENCES jobs(project_id, id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (project_id, storage_object_id) REFERENCES storage_objects(project_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE provider_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    derivative_id uuid NOT NULL,
    provider text NOT NULL,
    remote_name text NOT NULL,
    remote_uri text NOT NULL,
    status text NOT NULL CHECK (status IN ('processing', 'active', 'failed', 'expired', 'deleted')),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, remote_name),
    FOREIGN KEY (project_id, derivative_id) REFERENCES derivatives(project_id, id) ON DELETE CASCADE
);
CREATE INDEX provider_files_lookup ON provider_files(derivative_id, provider, status);

CREATE TABLE ai_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id uuid,
    provider text NOT NULL,
    model text NOT NULL,
    purpose text NOT NULL,
    request_fingerprint text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled')),
    input_tokens bigint CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens bigint CHECK (output_tokens IS NULL OR output_tokens >= 0),
    duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
    estimated_cost_microusd bigint CHECK (estimated_cost_microusd IS NULL OR estimated_cost_microusd >= 0),
    pricing_version text,
    error jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (estimated_cost_microusd IS NULL OR pricing_version IS NOT NULL),
    FOREIGN KEY (project_id, job_id) REFERENCES jobs(project_id, id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX ai_calls_project_time ON ai_calls(project_id, created_at);
COMMIT;

-- Service invariants to test when implementing the application:
-- * Every user-facing read/write checks project ownership from verified identity.
--   Composite project FKs prevent mixed-project references, not unauthorized reads.
-- * Network/AI/render work never holds a DB transaction open.
-- * Publication locks project, job and object rows in a consistent order; checks
--   project active, current lease token, verified object and correct purpose.
-- * Verified object keys/content are immutable; retries reserve new object keys.
-- * Source/segment ranges remain valid for all retained editing versions.
-- * Next jobs and results commit together; delivery is at least once.
-- * Current-version updates use CAS; stale jobs cannot promote another version.
-- * Search always scopes one project/profile; embedding spaces never mix.
-- * Multipart limits and full hashes validate uploads; ETag is not SHA-256.
-- * Deletion stops writers, cleans S3/provider objects, then removes metadata.
