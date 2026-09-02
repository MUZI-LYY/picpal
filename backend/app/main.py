"""FastAPI 入口：API + 静态验收界面。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .api.conversations import router as conversations_router
from .api.invites import router as invites_router
from .api.runs_plans import router as runs_plans_router
from .core.config import STATIC_DIR
from .core.errors import AppError, error_body
from .db.base import Base
from .db.errors import ActiveRunConflict, IdempotencyConflict
from .db.session import get_engine
from .services.conversation_service import ConversationServiceError
from .services.requirement_collector import RequirementCollectionError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表：生产环境数据库在 /tmp，首次启动需要自动创建。
    Base.metadata.create_all(bind=get_engine())
    yield


app = FastAPI(title="北京 AI 旅行规划助手", version="0.1.0", lifespan=lifespan)

app.include_router(router)
app.include_router(conversations_router)
app.include_router(invites_router)
app.include_router(runs_plans_router)

photo_dir = STATIC_DIR / "photos"
if photo_dir.exists():
    app.mount(
        "/api/v1/photo-assets",
        StaticFiles(directory=str(photo_dir)),
        name="photo-assets",
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.http_status, content=error_body(exc.code, exc.message))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content=error_body("http_error", str(detail)))


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": ".".join(str(part) for part in item["loc"] if part != "body") or None,
            "code": item["type"],
            "message": item["msg"],
        }
        for item in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "请求参数无效", details=details),
    )


@app.exception_handler(RequirementCollectionError)
async def requirement_error_handler(request: Request, exc: RequirementCollectionError):
    status = 409 if exc.code == "clarification_already_answered" else 422
    return JSONResponse(status_code=status, content=error_body(exc.code, exc.message))


@app.exception_handler(ConversationServiceError)
async def conversation_service_error_handler(request: Request, exc: ConversationServiceError):
    status_by_code = {
        "not_found": 404,
        "run_in_progress": 409,
        "plan_version_conflict": 409,
        "clarification_already_answered": 409,
        "invalid_slot_value": 422,
    }
    status = status_by_code.get(exc.code, 500 if exc.code == "internal_error" else 400)
    message = "服务内部错误" if status == 500 else exc.message
    return JSONResponse(status_code=status, content=error_body(exc.code, message))


@app.exception_handler(IdempotencyConflict)
async def idempotency_error_handler(request: Request, exc: IdempotencyConflict):
    return JSONResponse(
        status_code=409,
        content=error_body("idempotency_conflict", "消息标识已用于不同请求"),
    )


@app.exception_handler(ActiveRunConflict)
async def active_run_error_handler(request: Request, exc: ActiveRunConflict):
    return JSONResponse(
        status_code=409,
        content=error_body("run_in_progress", "当前对话已有运行中的任务"),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # 不向用户泄露堆栈
    return JSONResponse(status_code=500, content=error_body("internal_error", "服务内部错误"))


# 一次性最小验收界面
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
