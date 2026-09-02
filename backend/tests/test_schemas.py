"""契约测试：三大 JSON Schema 2020-12 合法/非法示例 + Pydantic 校验。"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from app.schemas import ParsedTripRequest, PhotoSpotRetrievalHit, ItineraryPlan

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "app" / "schemas" / "json_schemas"


def _read(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate_schema(name: str, example_name: str, should_pass: bool) -> None:
    schema = _read(f"{name}.schema.json")
    example = _read(f"{name}.{example_name}.example.json")
    validator = jsonschema.Draft202012Validator(schema)
    if should_pass:
        validator.validate(example)
    else:
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(example)


@pytest.mark.parametrize("name", ["parsed_trip_request", "photo_spot_retrieval_hit", "itinerary_plan"])
def test_valid_examples_pass_schema(name: str) -> None:
    _validate_schema(name, "valid", should_pass=True)


@pytest.mark.parametrize("name", ["parsed_trip_request", "photo_spot_retrieval_hit", "itinerary_plan"])
def test_invalid_examples_fail_schema(name: str) -> None:
    _validate_schema(name, "invalid", should_pass=False)


def test_pydantic_parsed_request_validates() -> None:
    data = _read("parsed_trip_request.valid.example.json")
    ParsedTripRequest.model_validate(data)


def test_pydantic_parsed_request_rejects_bad_days() -> None:
    data = _read("parsed_trip_request.valid.example.json")
    data["days"] = 6
    with pytest.raises(Exception):
        ParsedTripRequest.model_validate(data)


def test_pydantic_parsed_request_rejects_other_city() -> None:
    data = _read("parsed_trip_request.valid.example.json")
    data["city"] = "上海"
    with pytest.raises(Exception):
        ParsedTripRequest.model_validate(data)


def test_pydantic_photo_spot_allows_text_only_hits() -> None:
    data = _read("photo_spot_retrieval_hit.valid.example.json")
    data["hits"][0]["reference_photos"] = []
    data["hits"][0]["source_refs"] = []

    parsed = PhotoSpotRetrievalHit.model_validate(data)

    assert parsed.hits[0].reference_photos == []
    assert parsed.hits[0].source_refs == []


def test_pydantic_itinerary_plan_validates() -> None:
    data = _read("itinerary_plan.valid.example.json")
    ItineraryPlan.model_validate(data)
