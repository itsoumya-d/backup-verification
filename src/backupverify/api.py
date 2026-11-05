from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .pipeline import BackupVerifier


class IngestIn(BaseModel):
    snapshot_id: str
    job_id: str
    created_at: str | None = None
    files: list[dict[str, Any]]


class VerifyIn(BaseModel):
    storage: list[dict[str, Any]] = Field(default_factory=list)


class RestoreIn(BaseModel):
    paths: list[str] = Field(default_factory=list)


def _summary(summary) -> dict[str, Any]:
    return {
        "received": summary.received,
        "created": summary.created,
        "unchanged": summary.unchanged,
        "rejected": summary.rejected,
        "dead_letters": [letter.__dict__ for letter in summary.dead_letters],
        "audit": [entry.__dict__ | {"at": entry.at.isoformat()} for entry in summary.audit],
    }


def create_app(verifier: BackupVerifier | None = None) -> FastAPI:
    state = verifier or BackupVerifier()
    app = FastAPI(title="Backup verification", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/snapshots")
    def ingest(payload: IngestIn) -> dict[str, Any]:
        return _summary(state.ingest(payload.model_dump()))

    @app.post("/snapshots/{snapshot_id}/verify")
    def verify(snapshot_id: str, payload: VerifyIn) -> dict[str, Any]:
        try:
            issues = state.verify(snapshot_id, payload.storage)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "snapshot_id": snapshot_id,
            "ok": not issues,
            "issues": [item.__dict__ for item in issues],
        }

    @app.post("/snapshots/{snapshot_id}/restore-plan")
    def restore_plan(snapshot_id: str, payload: RestoreIn) -> dict[str, Any]:
        try:
            plan = state.restore_plan(snapshot_id, payload.paths)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return plan.as_dict()

    return app


app = create_app()
