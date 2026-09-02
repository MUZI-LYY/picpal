"""对话式 MVP 的 OpenAPI 3.1 契约测试。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[2]
SPEC_PATH = BACKEND_DIR / "contracts" / "openapi-v1.yaml"
FIXTURE_DIR = BACKEND_DIR / "contracts" / "fixtures"


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _validator(spec: dict[str, Any], schema_name: str) -> Draft202012Validator:
    # 以完整 OpenAPI 文档作为解析根，确保 #/components/schemas/* 本地引用可解析。
    root = copy.deepcopy(spec)
    root["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    root["$ref"] = f"#/components/schemas/{schema_name}"
    return Draft202012Validator(root, format_checker=FormatChecker())


def _fixture(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_openapi_document_has_expected_shape(spec: dict[str, Any]):
    assert spec["openapi"] == "3.1.0"
    assert spec["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"
    assert spec["info"]["version"] == "1.0.0"
    assert len(spec["paths"]) == 7
    assert "cookieAuth" in spec["components"]["securitySchemes"]


def test_all_references_are_local_and_allowlisted(spec: dict[str, Any]):
    references = [node["$ref"] for node in _walk(spec) if isinstance(node, dict) and "$ref" in node]
    assert references
    assert all(ref.startswith("#/components/") for ref in references)
    assert not any(".." in ref or "://" in ref for ref in references)
    for ref in references:
        target: Any = spec
        for token in ref.removeprefix("#/").split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
        assert target is not None


def test_operation_ids_are_unique_and_success_responses_are_typed(spec: dict[str, Any]):
    operation_ids: list[str] = []
    for path, path_item in spec["paths"].items():
        assert path.startswith("/api/v1/")
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_ids.append(operation["operationId"])
            success_responses = [
                response
                for code, response in operation["responses"].items()
                if str(code).startswith("2")
            ]
            assert success_responses, f"{method.upper()} {path} 缺少成功响应"
            for response in success_responses:
                assert "content" in response, f"{method.upper()} {path} 成功响应缺少 content"
                assert "schema" in response["content"]["application/json"]
    assert len(operation_ids) == len(set(operation_ids))


def test_mutating_operations_require_idempotency_key(spec: dict[str, Any]):
    for path in (
        "/api/v1/conversations",
        "/api/v1/conversations/{conversation_id}/messages",
    ):
        parameters = spec["paths"][path]["post"]["parameters"]
        assert {item.get("$ref") for item in parameters} >= {
            "#/components/parameters/IdempotencyKey"
        }


@pytest.mark.parametrize(
    ("fixture_name", "schema_name"),
    [
        ("create-conversation.request.json", "CreateConversationRequest"),
        ("answer-days.request.json", "CreateMessageRequest"),
        ("revise-plan.request.json", "CreateMessageRequest"),
        ("conversation-turn-clarification.response.json", "ConversationTurnResponse"),
        ("conversation-turn-run-started.response.json", "ConversationTurnResponse"),
        ("run-running.response.json", "RunResponse"),
        ("run-failed.response.json", "RunResponse"),
        ("conversation-list-empty.response.json", "ConversationListResponse"),
        ("plan-version-conflict.response.json", "ApiErrorResponse"),
        ("plan-version-validated.response.json", "PlanVersionResponse"),
        ("featured-photo-spots.response.json", "FeaturedPhotoSpotListResponse"),
        ("health.response.json", "HealthResponse"),
    ],
)
def test_contract_fixture_is_valid(spec: dict[str, Any], fixture_name: str, schema_name: str):
    _validator(spec, schema_name).validate(_fixture(fixture_name))


def test_unknown_request_fields_are_rejected(spec: dict[str, Any]):
    payload = _fixture("create-conversation.request.json")
    payload["attachment"] = {"fake": True}
    with pytest.raises(ValidationError):
        _validator(spec, "CreateConversationRequest").validate(payload)


def test_days_answer_outside_mvp_range_is_rejected(spec: dict[str, Any]):
    payload = _fixture("answer-days.request.json")
    payload["structured_answer"]["value"] = 6
    with pytest.raises(ValidationError):
        _validator(spec, "CreateMessageRequest").validate(payload)


def test_specified_date_requires_a_real_date(spec: dict[str, Any]):
    requirements = _fixture("conversation-turn-run-started.response.json")["data"][
        "conversation"
    ]["requirements"]
    requirements["date_status"] = "specified"
    requirements["start_date"] = None
    with pytest.raises(ValidationError):
        _validator(spec, "RequirementsSnapshot").validate(requirements)


def test_pending_date_requires_null_start_date(spec: dict[str, Any]):
    requirements = _fixture("conversation-turn-run-started.response.json")["data"][
        "conversation"
    ]["requirements"]
    requirements["date_status"] = "pending"
    requirements["start_date"] = "2026-10-01"
    with pytest.raises(ValidationError):
        _validator(spec, "RequirementsSnapshot").validate(requirements)


def test_plan_wrapper_and_snapshot_ids_are_consistent():
    version = _fixture("plan-version-validated.response.json")["data"]
    assert version["id"] == version["plan"]["plan_id"]
    assert version["status"] == version["plan"]["status"] == "validated"
    assert version["retrieval_run_ids"]
    assert version["knowledge_index_version"]


def test_failed_run_requires_error_and_finished_at(spec: dict[str, Any]):
    payload = _fixture("run-failed.response.json")
    payload["data"]["error"] = None
    payload["data"]["finished_at"] = None
    with pytest.raises(ValidationError):
        _validator(spec, "RunResponse").validate(payload)
