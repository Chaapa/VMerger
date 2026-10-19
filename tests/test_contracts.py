import math
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from vmerger.contracts import Analysis, Clip, StoryPlan, canonical_hash, normalize_embedding, validate_plan


@pytest.fixture
def asset():
    key = str(uuid4())
    return key, {key: {"kind": "video", "duration_us": 10_000_000, "metadata": {}}}


def test_plan_boundaries_and_missing_asset(asset):
    key, assets = asset
    plan = StoryPlan(title="Valid", summary="", clips=[Clip(asset_id=key, start=1, end=5)])
    assert validate_plan(plan, assets, 60) == 4
    with pytest.raises(ValueError, match="duration budget"):
        validate_plan(plan, assets, 3)
    plan.clips[0].end = 11
    with pytest.raises(ValueError, match="source"):
        validate_plan(plan, assets, 60)
    with pytest.raises(ValueError, match="this project"):
        validate_plan(plan, {}, 60)


@pytest.mark.parametrize("start,end", [(5, 4), (5, 5), (0, 0.1)])
def test_invalid_ranges(asset, start, end):
    key, assets = asset
    with pytest.raises(ValueError):
        validate_plan(
            StoryPlan(title="Bad", summary="", clips=[Clip(asset_id=key, start=start, end=end)]), assets, 60
        )


def test_reject_arbitrary_effect_and_extra_fields(asset):
    with pytest.raises(ValidationError):
        Clip(asset_id=asset[0], start=0, end=1, effect="movie=http://169.254.169.254/")
    with pytest.raises(ValidationError):
        Clip(asset_id=asset[0], start=0, end=1, command="rm -rf /")
    with pytest.raises(ValidationError):
        Analysis(scenes=[{"start": 2, "end": 1, "description": "Invalid"}])


def test_music_requires_scoped_license(asset):
    key, assets = asset
    music_id = str(uuid4())
    plan = StoryPlan(
        title="Music", summary="", clips=[Clip(asset_id=key, start=0, end=1)], music_asset_id=music_id
    )
    with pytest.raises(ValueError, match="licensed"):
        validate_plan(plan, assets, 60)
    assets[music_id] = {"kind": "audio", "metadata": {"license_confirmed": True}}
    assert validate_plan(plan, assets, 60) == 1


@given(st.floats(min_value=0.01, max_value=1000, allow_nan=False))
def test_normalization_unit_length(x):
    result = normalize_embedding([x] * 768)
    assert math.isclose(sum(v * v for v in result), 1, abs_tol=1e-10)


@pytest.mark.parametrize("values", [[], [0.0] * 768, [math.nan] * 768, [math.inf] * 768])
def test_reject_bad_embeddings(values):
    with pytest.raises(ValueError):
        normalize_embedding(values)


def test_hash_stable():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
