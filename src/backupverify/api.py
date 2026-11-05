from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from .auth import load_api_keys, require_role
from .db import SessionLocal, init_db
from .service import BackupService, ConflictError, InvalidSnapshot, NotFoundError


class IngestIn(BaseModel):
    snapshot_id: str
    job_id: str
    created_at: str | None = None
    files: list[dict[str, Any]]


class StorageIn(BaseModel):
    objects: list[dict[str, Any]] = Field(default_factory=list)


class VerifyIn(BaseModel):
    storage: list[dict[str, Any]] | None = None


class RestoreIn(BaseModel):
    paths: list[str] = Field(default_factory=list)


def create_app(
    session_factory: sessionmaker = SessionLocal,
    api_keys: dict[str, str] | None = None,
    init_database: bool = True,
) -> FastAPI:
    if init_database:
        init_db()
    keys = api_keys or load_api_keys()
    app = FastAPI(title="Backup verification service", version="1.0.0")

    def db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    operator = require_role("operator", keys)
    viewer = require_role("viewer", keys)
    admin = require_role("admin", keys)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready(session: Session = Depends(db_session)) -> dict[str, str]:
        BackupService(session).ready()
        return {"status": "ready"}

    @app.post("/snapshots")
    def ingest(payload: IngestIn, session: Session = Depends(db_session), _: str = Depends(operator)) -> dict[str, Any]:
        try:
            result = BackupService(session).ingest(payload.model_dump())
        except InvalidSnapshot as exc:
            raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": result.status, "snapshot_id": result.snapshot_id, "files": result.files}

    @app.get("/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str, session: Session = Depends(db_session), _: str = Depends(viewer)) -> dict[str, Any]:
        try:
            return BackupService(session).get_snapshot(snapshot_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/storage/objects")
    def register_storage(payload: StorageIn, session: Session = Depends(db_session), _: str = Depends(operator)) -> dict[str, int]:
        return {"registered": BackupService(session).register_storage(payload.objects)}

    @app.post("/snapshots/{snapshot_id}/verify")
    def verify(
        snapshot_id: str,
        payload: VerifyIn | None = None,
        session: Session = Depends(db_session),
        _: str = Depends(operator),
    ) -> dict[str, Any]:
        try:
            issues = BackupService(session).verify(snapshot_id, payload.storage if payload else None)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "snapshot_id": snapshot_id,
            "ok": not issues,
            "issues": [item.__dict__ for item in issues],
        }

    @app.post("/snapshots/{snapshot_id}/restore-plan")
    def restore_plan(
        snapshot_id: str,
        payload: RestoreIn,
        session: Session = Depends(db_session),
        _: str = Depends(operator),
    ) -> dict[str, Any]:
        try:
            return BackupService(session).restore_plan(snapshot_id, payload.paths).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/audit")
    def audit(session: Session = Depends(db_session), _: str = Depends(admin)) -> dict[str, Any]:
        return {"audit": BackupService(session).audit()}

    return app


app = create_app()
