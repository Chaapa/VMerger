# VMerger

Turn a folder of videos into stories. Describe changes in a chat; the system plans and renders the edit.

**Implementation in progress.** Architecture and quality specifications are recorded in [`docs/architecture.md`](docs/architecture.md). Actual implementation status and reproducible validation will be documented as the vertical slice is built.

Media belongs in private S3 storage on your own server or NAS. PostgreSQL + pgvector holds metadata, immutable edit plans, job state and searchable scene embeddings. Workers use temporary scratch space for FFmpeg processing.

The commit sequence groups the implementation into milestones.
