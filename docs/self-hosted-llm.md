# Self-hosted LLMs and a backup GPU on Vast.ai

VMerger can call a hosted API, a model on your own GPU, or a model on a rented GPU. A compatible server only requires a different `base_url`, model and credential variable; agents and the editing pipeline remain shared. A NAS can store media while a separate machine performs inference.

**Implemented:** compatible endpoints and ordered creative-role fallback to already running servers. **Planned:** automatic GPU rental, model-startup waiting and rental release. The repository has no Vast.ai infrastructure-management client, and the application creates no paid resources.

## Connections

```mermaid
flowchart TB
    U["Browser: chat and results"] --> API["VMerger on your server"]
    API --> DB[("PostgreSQL + pgvector")]
    API --> S3[("S3 on your server / NAS")]
    DB --> W["Worker and AI router"]
    W --> P["1. Primary API / LLM"]
    P -->|"Network error, timeout, 429 or 5xx"| L["2. Your GPU and LLM"]
    L -->|"Transient unavailability"| T["3. SSH tunnel from your server"]
    T --> V["Already running Vast GPU + vLLM"]
    P --> C["JSON and edit-plan validation"]
    L --> C
    V --> C
    C --> F["FFmpeg worker"]
    F --> S3
```

Workers send model requests. The browser receives no inference credentials. Originals and completed films stay in S3; remote GPUs receive the selected roles' inputs, such as scene text and user requests. SSH encrypts the connection, but inference still executes on rented hardware.

## Serving a model

**vLLM** can provide the compatible Chat Completions server. Choose a supported instruct/chat model and check its license, JSON support and context capacity. Pin the vLLM version and weight revision in your deployment. GPU memory depends on weights, context and concurrency, not parameter count alone.

On a Linux GPU machine with vLLM, a compatible CUDA runtime, `MODEL_ID` and secret `VLLM_API_KEY` configured:

```sh
vllm serve "$MODEL_ID" \
  --served-model-name vmerger-planner \
  --host 127.0.0.1 --port 8000
```

Configure VMerger with `model = "vmerger-planner"` and `token_parameter = "max_tokens"`. Its `OWN_LLM_KEY` or `VAST_LLM_KEY` must match the server's `VLLM_API_KEY`. These are **inference keys, not Vast.ai rental API keys**. If the endpoint only supports JSON objects, set `response_format = "json_object"`; local Pydantic validation remains mandatory in either mode.

Keep vLLM behind SSH/VPN or an authenticating proxy. `--api-key`/`VLLM_API_KEY` does not protect every HTTP route. Commands, API support and authentication limits are documented in the [official vLLM guide](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/).

Text LLMs support director, music, editor and reviewer roles. The analyst needs a vision model accepting JPEGs; the current compatible adapter sends no audio. Embeddings need an explicitly configured embedding endpoint returning 768 values. A fully local deployment is possible, but one text-only endpoint does not provide all three capabilities.

## Connecting Vast.ai through your server

1. In your account, select sufficient GPU memory, pin the runtime image/version, allocate disk for weights and add an SSH public key. Begin with an already running instance. Model selection and quality need separate evaluation on your material.
2. Start vLLM inside the GPU environment as above. Get SSH host, port and user from the instance card. The inference port need not be public.
3. Open a tunnel from the VMerger server. This example assumes a **native worker on the same host as the SSH client**:

```sh
ssh -N \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18000:127.0.0.1:8000 \
  -p <SSH_PORT> <SSH_USER>@<SSH_HOST>
```

Verify the SSH host fingerprint on first connection. For persistent operation, manage the tunnel as a service that restarts after interruption. Native VMerger uses `base_url = "http://127.0.0.1:18000/v1"`. See [Vast.ai SSH and forwarding](https://docs.vast.ai/guides/instances/connect/ssh).

**In Docker Compose**, loopback belongs to each container. Run an SSH client service named `vast-tunnel` on the API/worker's private Docker network. Inside it, use `-g -L 0.0.0.0:18000:127.0.0.1:8000` without publishing host `ports`. Mount a dedicated SSH key and verified `known_hosts` only into that service. The application URL is then `http://vast-tunnel:18000/v1`. An equivalent `own-gpu-tunnel` reaches your own GPU. Add these services to your deployment; the base Compose file does not create them.

Before activating the route, check an authenticated `GET /v1/models` from the worker network, followed by a small `POST /v1/chat/completions` using the selected model and JSON schema. A model list or open TCP port alone does not establish inference readiness or schema compatibility. The owner performs these live checks; current project validation uses HTTP fixtures.

## Routes and backups

The complete [hybrid example](../config/ai.hybrid.example.toml) demonstrates hosted API → owned GPU → Vast GPU. Replace endpoints/models and save it as `config/ai.toml`, or set `AI_CONFIG_FILE=config/ai.hybrid.example.toml`. Add the referenced credentials to `.env`; recreate API/worker after environment changes.

To make your LLM primary, set `[default]` to `own_gpu` and model `vmerger-planner`, leaving only `vast_gpu` in each backup list. For a fully self-hosted setup, configure your own vision and embedding routes too; the example still points those roles at a hosted endpoint.

```toml
# Both providers must already be defined in the configuration.
[default]
provider = "own_gpu"
model = "vmerger-planner"

[fallbacks]
director = [{provider = "vast_gpu", model = "vmerger-planner"}]
music = [{provider = "vast_gpu", model = "vmerger-planner"}]
editor = [{provider = "vast_gpu", model = "vmerger-planner"}]
reviewer = [{provider = "vast_gpu", model = "vmerger-planner"}]
```

Each call tries its primary, then at most two ordered backups. Only network failures, timeouts and HTTP 429/5xx trigger switching. Missing credentials, other 4xx, refusals, truncation, invalid JSON and database errors stop the call. A valid reviewer rejection stays a rejection; another model is not asked to provide approval.

An empty list disables fallback. Analyst fallback is currently prohibited because video/audio capabilities differ. Embedding fallback is prohibited because vector spaces may be incompatible. Change those routes explicitly; a new embedding profile requires reindexing. Exhausted transient backups return a retryable error to the existing job mechanism. Every new call starts at its primary; there is no shared circuit breaker.

## Observability

**Quality and agents → AI team** displays primary routes, backup order and credential availability. This is configuration, not a health probe. Each `ai_calls` row records the actual provider/model, role, status, duration and known tokens for one attempt. Failed primary attempts remain even when a backup succeeds. Latency charts count attempts, and the provider-error counter includes failures before successful backup; neither is a count of failed user jobs.

A future controller needs separate measurements for backup-recovered jobs, switch frequency/cause, p95 model startup, GPU provisioning success, idle time and rental cost. These are not current dashboard metrics; they need logical-call IDs, switching events and billing data.

## Automatic rental after failure: a future controller

```mermaid
stateDiagram-v2
    [*] --> Primary
    Primary --> Done: Successful result
    Primary --> WaitingCapacity: Transient failure
    WaitingCapacity --> Provisioning: Budget and lease allow rental
    WaitingCapacity --> Failed: Budget or deadline exhausted
    Provisioning --> Loading: GPU created
    Provisioning --> Reconcile: Failed or uncertain API result
    Loading --> Ready: Tunnel and inference probe pass
    Loading --> Reconcile: Model loading timeout
    Ready --> Done: Resume saved job
    Done --> Idle: No waiting jobs
    Idle --> Reconcile: Idle TTL expired
    Reconcile --> Released: Instance released
```

This is a separate infrastructure controller, not a creative-agent tool. PostgreSQL records model profile, request/instance ID, state, lease, deadline, price cap and idle TTL. One lease per profile prevents ten workers from renting ten machines. After an uncertain API response, reconcile instances by request tag before buying again. Only the controller holds Vast credentials.

Check current price, GPU/VRAM, pinned image/weight revisions, instance limit and total budget. Waiting jobs release worker capacity and resume after readiness. Downloading weights may exceed a normal request, so provisioning must not run inside the existing 120-second transport timeout. A watchdog reconciles abandoned rentals after restarts and releases them under TTL; monitoring reports provisioning failures and spend.

Stopped Vast instances still incur storage charges. Cleanup must therefore include controlled deletion of unneeded instances, not only stop. Check compute, disk and bandwidth prices at rental time; see [Vast.ai billing](https://docs.vast.ai/guides/pricing). Automatic rental, budget control and this lifecycle **are not implemented or tested on real GPUs**.
