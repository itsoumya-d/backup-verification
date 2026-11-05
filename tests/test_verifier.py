from datetime import datetime, timezone

import pytest

from backupverify.pipeline import BackupVerifier

SHA_A = "a" * 64
SHA_B = "b" * 64


def snapshot(**overrides):
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


def storage():
    return [
        {"path": "/data/a.txt", "size": 10, "sha256": SHA_A},
        {"path": "/data/b.txt", "size": 20, "sha256": SHA_B},
    ]


def test_ingest_creates_and_is_idempotent():
    verifier = BackupVerifier()
    first = verifier.ingest(snapshot())
    assert first.created == 1
    second = verifier.ingest(snapshot())
    assert second.unchanged == 1
    assert len(verifier.snapshots) == 1


def test_ingest_rejects_duplicate_path_and_bad_checksum():
    verifier = BackupVerifier()
    dup = snapshot(files=[{"path": "/a", "size": 1, "sha256": SHA_A}, {"path": "/a", "size": 1, "sha256": SHA_B}])
    assert "duplicate file path" in verifier.ingest(dup).dead_letters[0].errors[0]
    bad = snapshot(files=[{"path": "/a", "size": 1, "sha256": "not-a-hash"}])
    assert "invalid sha256" in verifier.ingest(bad).dead_letters[0].errors[0]


def test_ingest_rejects_snapshot_change():
    verifier = BackupVerifier()
    verifier.ingest(snapshot())
    changed = snapshot(files=[{"path": "/data/a.txt", "size": 11, "sha256": SHA_A}])
    summary = verifier.ingest(changed)
    assert summary.rejected == 1
    assert "different files" in summary.dead_letters[0].errors[0]


def test_verify_accepts_matching_storage():
    verifier = BackupVerifier()
    verifier.ingest(snapshot())
    assert verifier.verify("snap-001", storage()) == []


def test_verify_reports_missing_size_checksum_and_unexpected():
    verifier = BackupVerifier()
    verifier.ingest(snapshot())
    bad_storage = [
        {"path": "/data/a.txt", "size": 11, "sha256": SHA_B},
        {"path": "/data/c.txt", "size": 5, "sha256": SHA_A},
    ]
    kinds = {item.kind for item in verifier.verify("snap-001", bad_storage)}
    assert {"size_mismatch", "checksum_mismatch", "missing_object", "unexpected_object"} <= kinds


def test_verify_unknown_snapshot_raises():
    with pytest.raises(ValueError, match="unknown snapshot"):
        BackupVerifier().verify("missing", [])


def test_restore_plan_filters_paths_and_totals_bytes():
    verifier = BackupVerifier()
    verifier.ingest(snapshot())
    plan = verifier.restore_plan("snap-001", ["/data/b.txt"])
    assert plan.total_bytes == 20
    assert plan.files[0].path == "/data/b.txt"
    assert plan.files[0].sha256 == SHA_B


def test_restore_plan_rejects_unknown_path():
    verifier = BackupVerifier()
    verifier.ingest(snapshot())
    with pytest.raises(ValueError, match="paths not in snapshot"):
        verifier.restore_plan("snap-001", ["/data/missing.txt"])


def test_audit_records_actions():
    verifier = BackupVerifier()
    verifier.ingest(snapshot())
    verifier.verify("snap-001", storage())
    actions = [entry.action for entry in verifier.audit]
    assert actions == ["created", "verified"]
