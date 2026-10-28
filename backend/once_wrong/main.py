"""FastAPI application factory for the persistent CSV demonstration backend."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from .models import Report, SubmissionRequest, Suggestion, Version
from .storage import Store
from .validation import MAX_FILE_BYTES, RULE_VERSION, SCHEMA_PROFILE, ApiError

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


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

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await run_in_threadpool(store.initialize, seed_demo=seed_demo)
        yield

    application = FastAPI(
        title="Once Wrong Demo API",
        version="0.1.0",
        description=(
            "demo_csv_v1 and team demo rules only. No official insurance validation, "
            "LLM, candidate revalidation or external submission is implemented."
        ),
        lifespan=lifespan,
    )
    application.state.store = store
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
        return {"status": "ok", "schemaProfileId": SCHEMA_PROFILE, "ruleVersion": RULE_VERSION}

    @application.get("/reports", response_model=list[Report], response_model_exclude_none=True)
    def list_reports():
        return store.list_reports()

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
            filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            if not filename.lower().endswith(".csv"):
                raise ApiError(422, "UNSUPPORTED_FILE_TYPE", "此示範目前只支援 UTF-8 CSV 檔。")
            raw = await file.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise ApiError(413, "FILE_TOO_LARGE", "檔案不可超過 2 MiB。")
            return await run_in_threadpool(store.add_version, report_id, raw, filename)
        finally:
            await file.close()

    @application.get(
        "/versions/{version_id}/issues/{issue_id:path}/suggestion", response_model=Suggestion
    )
    def get_suggestion(version_id: str, issue_id: str):
        return store.get_suggestion(version_id, issue_id)

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
