# Portfolio draft

Publish only after checking the linked CI run. This is draft text, not a post sent to LinkedIn.

## Suggested post

I built VMerger, a self-hosted prototype for turning a collection of videos into stories through a chat.

The interface has no editing timeline. A director, music selector, editing agent and reviewer produce a structured plan, and FFmpeg renders it. Media lives in private S3 storage on your own server; PostgreSQL and pgvector hold project state, source scenes, embeddings and immutable edit versions.

The engineering work I found most interesting was making the workflow safe to retry: concurrent job claims, lease tokens, cancellation, version checks and output verification before publication. I also added measurements that stay empty until there is evidence, rather than filling a dashboard with invented scores.

The local validation uses real PostgreSQL, SeaweedFS and FFmpeg. It covers authentication boundaries, concurrent workers, expired leases, stale renders, deduplication, version history and playback ranges. Deterministic provider fixtures verify orchestration; they are explicitly separate from evaluating the creative quality of a live model.

It is an alpha, with a working interface and server deployment configuration. The next step is a live Gemini evaluation on consented footage, followed by resumable uploads and a labelled quality dataset.

Repository: https://github.com/Chaapa/VMerger

## Demo outline

1. Open the real workspace and create a project.
2. Upload two short permitted clips and show that originals are stored in private S3.
3. With a configured Gemini key, analyze the clips, request a story and inspect the completed video. Until this step is actually tested, do not claim it has passed live validation.
4. Request one change in chat and show immutable version history.
5. Open the quality tab, explain which measurements are mechanical, which come from the model and which require people.
6. Show the real test/CI results and the deployment instructions.

No synthetic user counts, quality scores, production scale or cost savings are claimed.
