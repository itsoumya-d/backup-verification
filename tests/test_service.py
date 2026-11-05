from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backupverify.db import Base
from backupverify.service import BackupService, ConflictError, InvalidSnapshot, NotFoundError

SHA_A = "a" * 64
SHA_B = "b" * 64


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


def payload(**overrides):
    data = {
        "snapshot_id": "snap-001",
        "job_id": "job-001",
        "created_at": "2026-11-01T10:00:00Z",
        "files": [
            {"path": "/data/a.txt", "size": 10, "sha256": SHA_A},
            {"path": "/data/b.txt", "size": 20, "sha256": SHA_B},
        ],
    }
    data.update(overrides)
    return data


def test_service_ingest_is_idempotent(session):
    service = BackupService(session)
    assert service.ingest(payload()).status == "created"
    assert service.ingest(payload()).status == "unchanged"
    assert service.get_snapshot("snap-001")["files"][0]["path"] == "/data/a.txt"


def test_service_rejects_conflict_and_bad_manifest(session):
    service = BackupService(session)
    service.ingest(payload())
    with pytest.raises(ConflictError):
        service.ingest(payload(files=[{"path": "/data/a.txt", "size": 99, "sha256": SHA_A}]))
    with pytest.raises(InvalidSnapshot):
        service.ingest(payload(snapshot_id="bad", files=[{"path": "/x", "size": -1, "sha256": SHA_A}]))


def test_service_persists_storage_and_verifies(session):
    service = BackupService(session)
    service.ingest(payload())
    assert service.register_storage([
        {"path": "/data/a.txt", "size": 10, "sha256": SHA_A},
        {"path": "/data/b.txt", "size": 20, "sha256": SHA_B},
    ]) == 2
    assert service.verify("snap-001") == []


def test_service_reports_issues(session):
    service = BackupService(session)
    service.ingest(payload())
    issues = service.verify("snap-001", storage=[{"path": "/data/a.txt", "size": 11, "sha256": SHA_B}])
    kinds = {i.kind for i in issues}
    assert {"size_mismatch", "checksum_mismatch", "missing_object"} <= kinds


def test_service_restore_plan_and_audit(session):
    service = BackupService(session)
    service.ingest(payload())
    plan = service.restore_plan("snap-001", ["/data/b.txt"])
    assert plan.total_bytes == 20
    assert service.audit()[0]["action"] == "created"


def test_service_unknown_snapshot(session):
    with pytest.raises(NotFoundError):
        BackupService(session).get_snapshot("missing")
