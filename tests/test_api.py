from fastapi.testclient import TestClient

from backupverify.api import create_app

SHA_A = "a" * 64


def test_api_ingest_verify_and_restore():
    client = TestClient(create_app())
    payload = {
        "snapshot_id": "snap-001",
        "job_id": "job-001",
        "files": [{"path": "/a.txt", "size": 3, "sha256": SHA_A}],
    }
    ingest = client.post("/snapshots", json=payload)
    assert ingest.status_code == 200
    assert ingest.json()["created"] == 1

    verify = client.post("/snapshots/snap-001/verify", json={"storage": [{"path": "/a.txt", "size": 3, "sha256": SHA_A}]})
    assert verify.status_code == 200
    assert verify.json()["ok"] is True

    plan = client.post("/snapshots/snap-001/restore-plan", json={"paths": []})
    assert plan.status_code == 200
    assert plan.json()["total_bytes"] == 3


def test_api_unknown_snapshot_returns_404():
    client = TestClient(create_app())
    response = client.post("/snapshots/missing/verify", json={"storage": []})
    assert response.status_code == 404
