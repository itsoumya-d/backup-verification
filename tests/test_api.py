from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backupverify.api import create_app
from backupverify.db import Base

SHA_A = "a" * 64


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(
        session_factory=factory,
        api_keys={"admin-key": "admin", "operator-key": "operator", "viewer-key": "viewer"},
        init_database=False,
    )
    return TestClient(app)


def test_api_requires_auth_and_enforces_roles(client):
    assert client.post("/snapshots", json={}).status_code == 401
    response = client.post("/snapshots", json={}, headers={"X-API-Key": "viewer-key"})
    assert response.status_code == 403


def test_api_ingest_storage_verify_restore_and_audit(client):
    headers = {"X-API-Key": "operator-key"}
    payload = {
        "snapshot_id": "snap-001",
        "job_id": "job-001",
        "files": [{"path": "/a.txt", "size": 3, "sha256": SHA_A}],
    }
    assert client.post("/snapshots", json=payload, headers=headers).status_code == 200
    assert client.get("/snapshots/snap-001", headers={"X-API-Key": "viewer-key"}).status_code == 200

    storage = {"objects": [{"path": "/a.txt", "size": 3, "sha256": SHA_A}]}
    assert client.post("/storage/objects", json=storage, headers=headers).status_code == 200
    verify = client.post("/snapshots/snap-001/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["ok"] is True

    plan = client.post("/snapshots/snap-001/restore-plan", json={"paths": []}, headers=headers)
    assert plan.status_code == 200
    assert plan.json()["total_bytes"] == 3

    audit = client.get("/audit", headers={"X-API-Key": "admin-key"})
    assert audit.status_code == 200
    assert audit.json()["audit"]


def test_api_unknown_snapshot_returns_404(client):
    response = client.post(
        "/snapshots/missing/verify", headers={"X-API-Key": "operator-key"}
    )
    assert response.status_code == 404
