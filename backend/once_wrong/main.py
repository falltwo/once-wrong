"""Persistent report API with on-demand, rule-verified AI review."""

import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from .ai_service import ReviewService
from .models import Report, SubmissionRequest, Suggestion, Version
from .storage import Store
from .validation import MAX_FILE_BYTES, RULE_VERSION, SCHEMA_PROFILE, ApiError

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
REPO_ROOT = Path(__file__).resolve().parents[2]


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".csv"):
        raise ApiError(422, "UNSUPPORTED_FILE_TYPE", "目前只支援 UTF-8 CSV 檔。")
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "檔案不可超過 2 MiB。")
    return raw, filename


def _seed_setting() -> bool:
    value = os.environ.get("ONCE_WRONG_SEED_DEMO", "true").strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError("ONCE_WRONG_SEED_DEMO must be true or false")
    return value in {"true", "1", "yes", "on"}


def create_app(
    database_path: str | Path | None = None,
    *,
    seed_demo: bool | None = None,
    allowed_origins: list[str] | None = None,
    llm=None,
    knowledge_dir: str | Path | None = None,
    memory_path: str | Path | None = None,
    evaluation_path: str | Path | None = None,
) -> FastAPI:
    if database_path is None:
        database_path = os.environ.get("ONCE_WRONG_DB") or (
            Path(__file__).resolve().parents[1] / "data" / "once_wrong.sqlite3"
        )
    if seed_demo is None:
        seed_demo = _seed_setting()
    if allowed_origins is None:
        configured = os.environ.get("ONCE_WRONG_ALLOWED_ORIGINS")
        allowed_origins = (
            [origin.strip() for origin in configured.split(",") if origin.strip()]
            if configured is not None
            else DEFAULT_ORIGINS.copy()
        )
    store = Store(database_path)
    reviewer = ReviewService(llm, kb_dir=knowledge_dir, memory_path=memory_path)
    evaluation_path = Path(
        evaluation_path
        if evaluation_path is not None
        else os.environ.get(
            "ONCE_WRONG_EVALUATION", "docs/evaluation/2026-10-28-gemini-3.5-flash.json"
        )
    )
    if not evaluation_path.is_absolute():
        evaluation_path = REPO_ROOT / evaluation_path
    suggestion_locks: dict[tuple[str, str], Lock] = {}
    locks_guard = Lock()

    def review_suggestion(version_id: str, issue_id: str) -> dict:
        # Serialize the same issue within this worker without holding a DB transaction
        # or blocking the event loop during a synchronous provider call.
        with locks_guard:
            lock = suggestion_locks.setdefault((version_id, issue_id), Lock())
        with lock:
            version = store.get_version(version_id)
            cached = store.get_cached_suggestion(version_id, issue_id)
            if cached is not None:
                return cached
            payload = reviewer.review(version, version["reportId"], issue_id)
            store.save_suggestion(version_id, issue_id, payload)
            return payload

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await run_in_threadpool(store.initialize, seed_demo=seed_demo)
        yield

    application = FastAPI(
        title="Once Wrong API",
        version="0.2.0",
        description=(
            "Persistent demo and life-underwriting CSV validation, on-demand AI explanations "
            "and candidate revalidation. Submissions record internal confirmation only."
        ),
        lifespan=lifespan,
    )
    application.state.store = store
    application.state.reviewer = reviewer
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Source-SHA256", "Content-Disposition"],
    )

    @application.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError):
        content = {"code": error.code, "message": error.message}
        if error.details is not None:
            content["details"] = error.details
        return JSONResponse(content, status_code=error.status)

    @application.exception_handler(RequestValidationError)
    async def request_error_handler(request: Request, error: RequestValidationError):
        details = [
            {"location": list(item["loc"]), "type": item["type"], "message": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse(
            {"code": "INVALID_REQUEST", "message": "請求欄位或格式不正確。", "details": details},
            status_code=422,
        )

    @application.exception_handler(HTTPException)
    async def http_error_handler(request: Request, error: HTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(error.status_code, "HTTP_ERROR")
        return JSONResponse(
            {"code": code, "message": str(error.detail)},
            status_code=error.status_code,
            headers=error.headers,
        )

    @application.get("/health")
    def health():
        return {
            "status": "ok", "schemaProfileId": SCHEMA_PROFILE, "ruleVersion": RULE_VERSION,
            "ai": reviewer.health,
        }

    @application.get("/evaluations/latest")
    def latest_evaluation():
        try:
            return json.loads(evaluation_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError as error:
            raise ApiError(404, "EVALUATION_NOT_FOUND", "尚未提供 AI 審核評分結果。") from error
        except (OSError, ValueError) as error:
            raise ApiError(500, "EVALUATION_INVALID", "AI 審核評分檔無法讀取。") from error

    @application.get("/reports", response_model=list[Report], response_model_exclude_none=True)
    def list_reports():
        return store.list_reports()

    @application.post(
        "/reports", status_code=201, response_model=Report, response_model_exclude_none=True
    )
    async def create_report(
        name: str = Form(...), period: str = Form(...), file: UploadFile = File(...)
    ):
        try:
            name, period = name.strip(), period.strip()
            if not name or len(name) > 200:
                raise ApiError(422, "INVALID_REQUEST", "報表名稱須為 1 至 200 字。")
            if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period):
                raise ApiError(422, "INVALID_REQUEST", "報表期間須為 YYYY-MM 格式。")
            raw, filename = await _read_upload(file)
            return await run_in_threadpool(store.create_report, name, period, raw, filename)
        finally:
            await file.close()

    @application.get(
        "/reports/{report_id}", response_model=Report, response_model_exclude_none=True
    )
    def get_report(report_id: str):
        return store.get_report(report_id)

    @application.post(
        "/reports/{report_id}/versions",
        status_code=201,
        response_model=Version,
        response_model_exclude_none=True,
    )
    async def upload_version(report_id: str, file: UploadFile = File(...)):
        try:
            await run_in_threadpool(store.get_report, report_id)
            raw, filename = await _read_upload(file)
            return await run_in_threadpool(store.add_version, report_id, raw, filename)
        finally:
            await file.close()

    @application.get(
        "/versions/{version_id}/issues/{issue_id:path}/suggestion", response_model=Suggestion
    )
    async def get_suggestion(version_id: str, issue_id: str):
        return await run_in_threadpool(review_suggestion, version_id, issue_id)

    @application.get("/versions/{version_id}/source")
    def get_source(version_id: str):
        raw, filename, digest = store.get_source(version_id)
        return Response(
            content=raw,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
                "X-Source-SHA256": digest,
                "Cache-Control": "no-store",
            },
        )

    @application.post("/reports/{report_id}/submissions", status_code=204)
    def confirm_report(report_id: str, body: SubmissionRequest):
        store.confirm(report_id, body.versionId)
        return Response(status_code=204)

    return application


app = create_app()
