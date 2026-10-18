import hashlib
import json
import math
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scene(StrictModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=2000)
    speech: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Scene end must follow start")
        return self


class Analysis(StrictModel):
    scenes: list[Scene] = Field(min_length=1, max_length=40)


class Clip(StrictModel):
    asset_id: UUID
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    effect: Literal["none", "warm", "monochrome", "fade"] = "none"


class StoryPlan(StrictModel):
    title: str = Field(min_length=1, max_length=140)
    summary: str = Field(max_length=2000)
    clips: list[Clip] = Field(min_length=1, max_length=60)
    music_asset_id: UUID | None = None
    music_gain: float = Field(default=0.12, ge=0, le=0.25, allow_inf_nan=False)


class ProjectPlan(StrictModel):
    stories: list[StoryPlan] = Field(min_length=1, max_length=6)


class MusicChoice(StrictModel):
    music_asset_id: UUID | None = None
    rationale: str = Field(max_length=1000)


class Review(StrictModel):
    approved: bool
    issues: list[str] = Field(max_length=20)


def canonical_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def validate_plan(plan: StoryPlan, assets: dict, max_duration: float) -> float:
    total = 0.0
    for clip in plan.clips:
        asset = assets.get(str(clip.asset_id))
        if not asset or asset["kind"] != "video":
            raise ValueError("Clip must reference a video in this project")
        duration = asset["duration_us"] / 1_000_000
        if clip.end <= clip.start or clip.end > duration + 0.001:
            raise ValueError("Clip range exceeds its source")
        if clip.end - clip.start < 0.25:
            raise ValueError("Clip must be at least 250 ms")
        total += clip.end - clip.start
    if total > max_duration:
        raise ValueError("Output exceeds configured duration budget")
    if plan.music_asset_id:
        music = assets.get(str(plan.music_asset_id))
        if not music or music["kind"] != "audio" or not music["metadata"].get("license_confirmed"):
            raise ValueError("Music must come from the project's licensed library")
    return total


def normalize_embedding(values: list[float]) -> list[float]:
    if len(values) != 768 or not all(math.isfinite(x) for x in values):
        raise ValueError("Embedding must contain 768 finite values")
    norm = math.sqrt(sum(x * x for x in values))
    if norm < 1e-10:
        raise ValueError("Zero embedding is invalid")
    return [x / norm for x in values]
