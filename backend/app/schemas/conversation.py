"""正式对话 API 使用的需求补齐契约模型。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_message_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


class RequirementsSnapshot(BaseModel):
    city: Literal["北京"] = "北京"
    days: int | None = Field(default=None, ge=1, le=5)
    date_status: Literal["unknown", "specified", "pending"] = "unknown"
    start_date: date | None = None
    party_size: int | None = Field(default=None, ge=1)
    companion_types: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    must_exclude: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    photo_preferences: list[str] = Field(default_factory=list)
    pace: Literal["轻松", "适中", "紧凑"] | None = None
    lodging_text: str | None = Field(default=None, max_length=500)
    transport_preferences: list[str] = Field(default_factory=list)
    missing_slots: list[Literal["days", "start_date", "pace"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_date_and_refresh_missing_slots(self):
        if self.date_status == "specified" and self.start_date is None:
            raise ValueError("date_status=specified 时 start_date 必填")
        if self.date_status in {"unknown", "pending"} and self.start_date is not None:
            raise ValueError("date_status 为 unknown/pending 时 start_date 必须为空")

        missing: list[Literal["days", "start_date", "pace"]] = []
        if self.days is None:
            missing.append("days")
        if self.date_status == "unknown":
            missing.append("start_date")
        if self.pace is None:
            missing.append("pace")
        self.missing_slots = missing
        return self


class DaysAnswer(BaseModel):
    slot: Literal["days"]
    value: Literal[1, 2, 3, 4, 5]


class StartDateAnswer(BaseModel):
    slot: Literal["start_date"]
    value: date | Literal["pending"]


class PaceAnswer(BaseModel):
    slot: Literal["pace"]
    value: Literal["轻松", "适中", "紧凑"]


StructuredAnswer = Annotated[
    Union[DaysAnswer, StartDateAnswer, PaceAnswer],
    Field(discriminator="slot"),
]


class CreateMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_message_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    reply_to_message_id: str | None = Field(default=None, max_length=128)
    structured_answer: StructuredAnswer | None = None
    base_plan_id: str | None = Field(default=None, max_length=128)


class ClarificationOption(BaseModel):
    label: str = Field(min_length=1)
    value: int | str


class ClarificationContent(BaseModel):
    kind: Literal["clarification"] = "clarification"
    slot: Literal["days", "start_date", "pace"]
    control: Literal["single_select", "date_or_pending"]
    options: list[ClarificationOption]
    allow_pending: bool


class RequirementCollectionResult(BaseModel):
    requirements: RequirementsSnapshot
    clarification: ClarificationContent | None
    ready: bool


class ConversationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    status: Literal[
        "collecting_requirements", "generating", "completed", "failed", "archived"
    ]
    requirements: RequirementsSnapshot
    latest_plan_id: str | None
    active_run_id: str | None
    created_at: datetime
    updated_at: datetime


class MessageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content_type: Literal[
        "text", "clarification", "run_started", "plan_created", "plan_updated", "error"
    ]
    text: str
    structured_content: dict[str, Any] | None
    reply_to_message_id: str | None
    run_id: str | None
    plan_id: str | None
    created_at: datetime


class RunStageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal[
        "understanding_request",
        "resolving_pois",
        "planning_routes",
        "recommending_lodging",
        "retrieving_photo_spots",
        "validating",
    ]
    label: str
    status: Literal["waiting", "running", "succeeded", "failed", "skipped"]
    started_at: datetime | None
    completed_at: datetime | None


class RunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    kind: Literal["initial_plan", "revision"]
    status: Literal["queued", "running", "succeeded", "failed"]
    trigger_message_id: str
    base_plan_id: str | None
    result_plan_id: str | None
    current_stage: str | None
    stages: list[RunStageView]
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ConversationTurnData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationView
    accepted_message: MessageView
    assistant_messages: list[MessageView]
    active_run: RunView | None
    latest_plan: dict[str, Any] | None


class ConversationTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: ConversationTurnData


class ConversationSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    preview: str
    status: Literal[
        "collecting_requirements", "generating", "completed", "failed", "archived"
    ]
    latest_plan_id: str | None
    updated_at: datetime


class ForwardPageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_next: bool
    next_cursor: str | None


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ConversationSummaryView]
    meta: ForwardPageMeta


class BackwardPageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_more: bool
    before_cursor: str | None


class ConversationSnapshotData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationView
    messages: list[MessageView]
    message_page: BackwardPageMeta
    active_run: RunView | None
    latest_plan: dict[str, Any] | None


class ConversationSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: ConversationSnapshotData


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: RunView


class PlanVersionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    run_id: str
    version: int
    base_plan_id: str | None
    status: Literal["validated"]
    changed_days: list[int]
    change_summary: list[str]
    plan: dict[str, Any]
    retrieval_run_ids: list[str]
    knowledge_index_version: str
    created_at: datetime


class PlanVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: PlanVersionView
