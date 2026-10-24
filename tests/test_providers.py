import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from vmerger import media
from vmerger.ai_config import ProviderConfig, Route, RoutingConfig, load_routing, public_status
from vmerger.config import settings
from vmerger.contracts import Review
from vmerger.providers import CompatibleAdapter, ProviderRouter


@pytest.fixture
def routing_file(tmp_path, monkeypatch):
    path = tmp_path / "ai.toml"
    path.write_text("""frame_samples = 2
[providers.local]
adapter = "openai_compatible"
api_key_env = "VMERGER_TEST_KEY"
base_url = "http://localhost:9999/v1"
[default]
provider = "local"
model = "fixture-vision"
[routes.reviewer]
provider = "local"
model = "fixture-reviewer"
[routes.embedding]
provider = "local"
model = "fixture-embedding"
""")
    monkeypatch.setattr(settings(), "ai_config_file", path)
    monkeypatch.setenv("VMERGER_TEST_KEY", "fixture-secret-not-a-real-key")
    return path


@pytest.fixture
def mock_http(monkeypatch):
    original = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            "vmerger.providers.httpx.Client",
            lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
        )

    return install


def completion(text='{"approved": true, "issues": []}', reason="stop", refusal=None):
    return {
        "choices": [{"finish_reason": reason, "message": {"content": text, "refusal": refusal}}],
        "usage": {"prompt_tokens": 17, "completion_tokens": 8},
    }


def test_routes_are_snapshotted_and_public_config_hides_secrets(routing_file):
    first = ProviderRouter({"project_id": "fixture", "id": None})
    assert first.describe("director")["model"] == "fixture-vision"
    assert first.describe("reviewer")["model"] == "fixture-reviewer"
    assert first.describe("analyst")["input_mode"] == "sampled_frames"
    status = public_status()
    assert status["ai_available"] and status["embedding_available"]
    assert "fixture-secret" not in json.dumps(status) and "localhost" not in json.dumps(status)
    routing_file.write_text(
        routing_file.read_text().replace('model = "fixture-reviewer"', 'model = "replacement"')
    )
    second = ProviderRouter({"project_id": "fixture", "id": None})
    assert first.describe("reviewer")["model"] == "fixture-reviewer"
    assert second.describe("reviewer")["model"] == "replacement"
    assert first.adapter("director") is first.adapter("reviewer")
    with pytest.raises(ValueError, match="Unknown AI role"):
        first.describe("not-a-role")


def test_configuration_validation_and_partial_availability(routing_file, monkeypatch):
    monkeypatch.delenv("VMERGER_TEST_KEY")
    assert not public_status()["ai_available"]
    with pytest.raises(ValueError, match="credentials"):
        ProviderRouter({}).adapter("director")
    routing_file.write_text(
        routing_file.read_text().replace(
            'api_key_env = "VMERGER_TEST_KEY"', 'allow_no_key = true\napi_key_env = "VMERGER_TEST_KEY"'
        )
    )
    assert public_status()["planning_available"]
    routing_file.write_text("invalid TOML [")
    assert public_status()["config_error"]
    routing_file.unlink()
    assert public_status()["config_error"]


def test_profiles_separate_models_endpoints_and_preprocessing(routing_file):
    config = load_routing()
    original = config.embedding_profile
    provider = config.providers["local"]
    for update in (
        {"base_url": "http://localhost:9998/v1"},
        {"query_prefix": "query: "},
        {"document_prefix": "passage: "},
    ):
        changed = config.model_copy(update={"providers": {"local": provider.model_copy(update=update)}})
        assert changed.embedding_profile != original
    changed = config.model_copy(update={"routes": {"embedding": Route(provider="local", model="different")}})
    assert changed.embedding_profile != original
    alias = config.model_copy(
        update={
            "providers": {"renamed": provider},
            "routes": {"embedding": Route(provider="renamed", model="fixture-embedding")},
        }
    )
    assert alias.embedding_profile == original


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/x",
        "https://key:secret@example.com/v1",
        "https://example.com/v1?key=secret",
        "https://example.com/#fragment",
    ],
)
def test_reject_unsafe_endpoint_configuration(url):
    with pytest.raises(ValidationError):
        ProviderConfig(adapter="openai_compatible", api_key_env="KEY", base_url=url)


def test_legacy_configuration_and_invalid_routes(monkeypatch):
    monkeypatch.setattr(settings(), "ai_config_file", None)
    config = load_routing()
    assert config.embedding_profile == f"{settings().embedding_model}:text-v1:768"
    data = config.model_dump()
    data["routes"] = {}
    with pytest.raises(ValidationError, match="explicit embedding"):
        RoutingConfig.model_validate(data)
    data["routes"] = {"embedding": {"provider": "missing", "model": "test"}}
    with pytest.raises(ValidationError, match="unknown provider"):
        RoutingConfig.model_validate(data)


def test_explicit_environment_credentials_take_precedence(monkeypatch):
    from vmerger.ai_config import api_key

    provider = ProviderConfig(adapter="gemini", api_key_env="GEMINI_API_KEY")
    monkeypatch.setattr(settings(), "gemini_api_key", "cached-file-fixture")
    # Compose injects an explicit empty value when live AI is disabled.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert api_key(provider, {"GEMINI_API_KEY": "file-fixture"}) == ""
    monkeypatch.setenv("GEMINI_API_KEY", "environment-fixture")
    assert api_key(provider, {"GEMINI_API_KEY": "file-fixture"}) == "environment-fixture"


@pytest.mark.parametrize(
    "mode,token_field", [("json_schema", "max_completion_tokens"), ("json_object", "max_tokens")]
)
def test_compatible_chat_protocol(routing_file, mock_http, mode, token_field):
    config = load_routing()
    adapter = CompatibleAdapter(
        config.providers["local"].model_copy(
            update={"response_format": mode, "token_parameter": token_field}
        ),
        "fixture-key",
    )

    def handle(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fixture-key"
        assert body["model"] == "chosen-model" and body[token_field] == 12000
        assert body["response_format"]["type"] == mode
        assert "JSON schema" in body["messages"][0]["content"]
        return httpx.Response(200, json=completion())

    mock_http(handle)
    text, incoming, outgoing = adapter.generate("chosen-model", "Review", Review, None, None, config)
    assert Review.model_validate_json(text).approved and (incoming, outgoing) == (17, 8)


def test_compatible_frames_are_timestamped_and_audio_is_rejected(routing_file, mock_http, monkeypatch):
    router = ProviderRouter({})
    monkeypatch.setattr(router, "audited", lambda role, purpose, fingerprint, operation: operation()[0])
    monkeypatch.setattr(media, "sample_frames", lambda *args: [(0.5, b"jpeg"), (1.5, b"jpeg")])
    answer = {"scenes": [{"start": 0, "end": 2, "description": "Test", "speech": ""}]}

    def handle(request):
        body = json.loads(request.content)
        parts = body["messages"][1]["content"]
        assert len(parts) == 5 and "without audio" in parts[0]["text"]
        assert "0.500" in parts[1]["text"] and parts[2]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )
        return httpx.Response(200, json=completion(json.dumps(answer)))

    mock_http(handle)
    assert router.analyze(Path("unused.mp4"), 2).scenes[0].speech == ""
    answer["scenes"][0]["speech"] = "Invented speech"
    with pytest.raises(ValueError, match="cannot transcribe"):
        router.analyze(Path("unused.mp4"), 2)


@pytest.mark.parametrize("reason,refusal", [("length", None), ("stop", "declined")])
def test_incomplete_or_refused_outputs_are_rejected(routing_file, mock_http, reason, refusal):
    mock_http(lambda request: httpx.Response(200, json=completion(reason=reason, refusal=refusal)))
    router = ProviderRouter({})
    with pytest.raises(ValueError, match="refused or incomplete"):
        router.adapter("reviewer").generate("test", "test", Review, None, None, router.routing)


@pytest.mark.parametrize(
    "status,error", [(400, ValueError), (429, ConnectionError), (503, ConnectionError), (302, ValueError)]
)
def test_http_errors_are_classified_without_provider_bodies(routing_file, mock_http, status, error):
    mock_http(lambda request: httpx.Response(status, text="secret provider body"))
    with pytest.raises(error) as caught:
        ProviderRouter({}).adapter("embedding").request("/embeddings", {})
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "failure,error", [(httpx.ReadTimeout, TimeoutError), (httpx.ConnectError, ConnectionError)]
)
def test_transport_failures_are_retryable(routing_file, mock_http, failure, error):
    def fail(request):
        raise failure("private diagnostics")

    mock_http(fail)
    with pytest.raises(error):
        ProviderRouter({}).adapter("embedding").request("/embeddings", {})


def test_embeddings_reorder_validate_dimensions_and_apply_prefixes(routing_file, mock_http, monkeypatch):
    router = ProviderRouter({})
    monkeypatch.setattr(router, "audited", lambda role, purpose, fingerprint, operation: operation()[0])
    adapter = router.adapter("embedding")
    adapter.config = adapter.config.model_copy(
        update={"query_prefix": "query: ", "document_prefix": "passage: "}
    )
    rows = [
        {"index": 1, "embedding": [0.0, 2.0] + [0.0] * 766},
        {"index": 0, "embedding": [2.0] + [0.0] * 767},
    ]
    bodies = []

    def handle(request):
        assert request.url.path == "/v1/embeddings"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"data": rows})

    mock_http(handle)
    vectors = router.embed(["a", "b"])
    assert vectors[0][0] == vectors[1][1] == 1
    assert bodies[-1]["input"] == ["passage: a", "passage: b"] and bodies[-1]["dimensions"] == 768
    adapter.config = adapter.config.model_copy(update={"send_dimensions": False})
    router.embed(["a", "b"], query=True)
    assert bodies[-1]["input"] == ["query: a", "query: b"] and "dimensions" not in bodies[-1]
    rows[0]["index"] = 0
    with pytest.raises(ValueError, match="indexes"):
        router.embed(["a", "b"])
    rows[0]["index"] = 1
    rows[0]["embedding"] = [1.0, 0.0]
    with pytest.raises(ValueError, match="768"):
        router.embed(["a", "b"])


def test_frame_sampling_rejects_invalid_budgets_and_empty_output(monkeypatch):
    with pytest.raises(ValueError, match="budget"):
        list(media.sample_frames(Path("unused"), 0, 2))
    monkeypatch.setattr(media, "run", lambda *args, **kwargs: b"")
    with pytest.raises(ValueError, match="missing"):
        list(media.sample_frames(Path("unused"), 2, 2))


@pytest.mark.integration
def test_mixed_endpoints_record_routes_and_invalid_outputs(project, routing_file, mock_http, monkeypatch):
    from vmerger.db import connect

    text = routing_file.read_text().replace(
        '[routes.reviewer]\nprovider = "local"', '[routes.reviewer]\nprovider = "review"'
    )
    routing_file.write_text(
        text
        + """
[providers.review]
adapter = "openai_compatible"
api_key_env = "VMERGER_REVIEW_KEY"
base_url = "http://review.local/v1"
"""
    )
    monkeypatch.setenv("VMERGER_REVIEW_KEY", "separate-fixture-key")
    invalid = False

    def handle(request):
        if request.url.path.endswith("/embeddings"):
            assert request.url.host == "localhost"
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [3.0] + [0.0] * 767}]})
        assert request.url.host == "review.local"
        assert request.headers["Authorization"] == "Bearer separate-fixture-key"
        return httpx.Response(
            200, json=completion("private invalid output" if invalid else '{"approved": true, "issues": []}')
        )

    mock_http(handle)
    router = ProviderRouter({"project_id": project["id"], "id": None})
    assert router.call("reviewer", "fixture request", Review).approved
    assert router.embed(["fixture text"])[0][0] == 1
    invalid = True
    with pytest.raises(ValidationError):
        router.call("reviewer", "fixture request", Review)
    with connect() as conn:
        rows = conn.execute(
            "SELECT provider,model,purpose,status,error,input_tokens FROM ai_calls WHERE project_id=%s ORDER BY created_at",
            (project["id"],),
        ).fetchall()
    assert [(r["provider"], r["model"], r["status"]) for r in rows] == [
        ("review", "fixture-reviewer", "succeeded"),
        ("local", "fixture-embedding", "succeeded"),
        ("review", "fixture-reviewer", "failed"),
    ]
    assert rows[0]["input_tokens"] == 17
    assert rows[-1]["error"] == {"type": "ValidationError"}
    assert "private invalid output" not in json.dumps(rows)


@pytest.mark.integration
def test_sample_frames_uses_real_ffmpeg(videos):
    frames = list(media.sample_frames(videos[0][0], 2, 2))
    assert [time for time, _ in frames] == [0.5, 1.5]
    assert all(jpeg.startswith(b"\xff\xd8") for _, jpeg in frames)
