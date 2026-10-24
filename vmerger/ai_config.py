"""Provider configuration is a job-scoped snapshot; secrets never enter its public view."""

import os
import tomllib
from typing import Literal
from urllib.parse import urlparse

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import settings
from .contracts import canonical_hash

Role = Literal["analyst", "director", "music", "editor", "reviewer", "embedding"]
ROLES = ("analyst", "director", "music", "editor", "reviewer", "embedding")


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    adapter: Literal["gemini", "openai_compatible"]
    api_key_env: str = Field(min_length=1)
    base_url: str = ""
    allow_no_key: bool = False
    response_format: Literal["json_schema", "json_object"] = "json_schema"
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_completion_tokens"
    send_dimensions: bool = True
    document_prefix: str = ""
    query_prefix: str = ""

    @model_validator(mode="after")
    def endpoint(self):
        if self.adapter == "openai_compatible":
            url = urlparse(self.base_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError(
                    "Compatible base_url must be an HTTP(S) endpoint without credentials or query"
                )
        return self


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    providers: dict[str, ProviderConfig]
    default: Route
    routes: dict[Role, Route]
    frame_samples: int = Field(default=12, ge=2, le=24)
    max_output_tokens: int = Field(default=12000, ge=256, le=32000)

    @model_validator(mode="after")
    def references(self):
        if "embedding" not in self.routes:
            raise ValueError("An explicit embedding route is required")
        for route in [self.default, *self.routes.values()]:
            if route.provider not in self.providers:
                raise ValueError("Route refers to an unknown provider")
        return self

    def route(self, role: Role) -> Route:
        if role not in ROLES:
            raise ValueError("Unknown AI role")
        return self.routes.get(role, self.default)

    @property
    def embedding_profile(self):
        route = self.route("embedding")
        provider = self.providers[route.provider]
        if provider.adapter == "gemini":
            # Preserve compatibility with already indexed Gemini scenes.
            return f"{route.model}:text-v1:768"
        identity = canonical_hash(
            {
                "adapter": provider.adapter,
                "endpoint": provider.base_url.rstrip("/"),
                "document_prefix": provider.document_prefix,
                "query_prefix": provider.query_prefix,
            }
        )[:16]
        return f"{provider.adapter}:{identity}:{route.model}:text-v1:768"


def load_routing() -> RoutingConfig:
    s = settings()
    if s.ai_config_file is not None:
        with s.ai_config_file.open("rb") as stream:
            return RoutingConfig.model_validate(tomllib.load(stream))
    # Explicit compatibility mode for installations predating configurable routing.
    return RoutingConfig(
        providers={"gemini": ProviderConfig(adapter="gemini", api_key_env="GEMINI_API_KEY")},
        default=Route(provider="gemini", model=s.gemini_model),
        routes={"embedding": Route(provider="gemini", model=s.embedding_model)},
    )


def api_key(provider: ProviderConfig, local_values: dict) -> str:
    # Settings preserves the existing GEMINI_API_KEY behavior; other names can be arbitrary.
    known = getattr(settings(), provider.api_key_env.lower(), None)
    return str(
        os.environ.get(
            provider.api_key_env, known if isinstance(known, str) else local_values.get(provider.api_key_env)
        )
        or ""
    )


def credentials(config: RoutingConfig) -> dict[str, str]:
    local_values = dotenv_values(".env")
    return {name: api_key(provider, local_values) for name, provider in config.providers.items()}


def public_status():
    try:
        config = load_routing()
        keys = credentials(config)
        routes = {}
        for role in ROLES:
            route = config.route(role)
            provider = config.providers[route.provider]
            routes[role] = {
                "provider": route.provider,
                "adapter": provider.adapter,
                "model": route.model,
                "configured": bool(keys[route.provider])
                or (provider.adapter == "openai_compatible" and provider.allow_no_key),
            }
        return {
            "ai_available": all(r["configured"] for r in routes.values()),
            "analysis_available": all(routes[r]["configured"] for r in ("analyst", "embedding")),
            "planning_available": all(
                routes[r]["configured"] for r in ("director", "music", "editor", "reviewer")
            ),
            "embedding_available": routes["embedding"]["configured"],
            "routes": routes,
            "embedding_profile": config.embedding_profile,
            "analysis_mode": "native_video" if routes["analyst"]["adapter"] == "gemini" else "sampled_frames",
            "config_error": False,
        }
    except (OSError, ValueError):
        return {
            "ai_available": False,
            "analysis_available": False,
            "planning_available": False,
            "embedding_available": False,
            "routes": {},
            "config_error": True,
        }
