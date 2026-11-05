from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .manifest import normalize_snapshot
from .models import RestoreFile, RestorePlan, Snapshot, VerificationIssue
from .tables import AuditRow, DeadLetterRow, SnapshotFileRow, SnapshotRow, StorageObjectRow


class ConflictError(Exception):
    pass


class NotFoundError(Exception):
    pass


class InvalidSnapshot(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class IngestResult:
    status: str
    snapshot_id: str
    files: int
    detail: str = ""


class BackupService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _audit(self, action: str, reference: str, detail: str = "") -> None:
        self.session.add(AuditRow(action=action, reference=reference, detail=detail))

    def _dead_letter(self, reference: str, payload: dict, errors: list[str]) -> None:
        self.session.add(DeadLetterRow(reference=reference, payload=json.dumps(payload), errors="; ".join(errors)))

    def ingest(self, payload: dict) -> IngestResult:
        snapshot_id = str(payload.get("snapshot_id") or "")
        try:
            snapshot = normalize_snapshot(payload)
        except ValueError as exc:
            self._dead_letter(snapshot_id, payload, [str(exc)])
            self._audit("rejected", snapshot_id, str(exc))
            self.session.commit()
            raise InvalidSnapshot([str(exc)]) from exc

        existing = self.session.scalar(select(SnapshotRow).where(SnapshotRow.snapshot_id == snapshot.snapshot_id))
        if existing is not None:
            if existing.fingerprint != snapshot.fingerprint():
                error = "snapshot already exists with different files"
                self._dead_letter(snapshot_id, payload, [error])
                self._audit("conflict", snapshot_id, error)
                self.session.commit()
                raise ConflictError(error)
            self._audit("unchanged", snapshot_id, f"files={len(snapshot.files)}")
            self.session.commit()
            return IngestResult("unchanged", snapshot_id, len(snapshot.files))

        row = SnapshotRow(
            snapshot_id=snapshot.snapshot_id,
            job_id=snapshot.job_id,
            created_at=snapshot.created_at,
            fingerprint=snapshot.fingerprint(),
        )
        self.session.add(row)
        self.session.flush()
        for entry in snapshot.files:
            self.session.add(SnapshotFileRow(snapshot_pk=row.id, path=entry.path, size=entry.size, sha256=entry.sha256))
        self._audit("created", snapshot_id, f"files={len(snapshot.files)}")
        self.session.commit()
        return IngestResult("created", snapshot_id, len(snapshot.files))

    def register_storage(self, objects: list[dict]) -> int:
        count = 0
        for item in objects:
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            size = int(item.get("size"))
            digest = str(item.get("sha256") or "").lower()
            existing = self.session.scalar(select(StorageObjectRow).where(StorageObjectRow.path == path))
            if existing is None:
                self.session.add(StorageObjectRow(path=path, size=size, sha256=digest))
            else:
                existing.size = size
                existing.sha256 = digest
                existing.updated_at = datetime.now(timezone.utc)
            count += 1
        self._audit("storage_registered", "storage", f"objects={count}")
        self.session.commit()
        return count

    def _snapshot(self, snapshot_id: str) -> SnapshotRow:
        row = self.session.scalar(select(SnapshotRow).where(SnapshotRow.snapshot_id == snapshot_id))
        if row is None:
            raise NotFoundError(f"unknown snapshot: {snapshot_id}")
        return row

    def verify(self, snapshot_id: str, storage: list[dict] | None = None) -> list[VerificationIssue]:
        row = self._snapshot(snapshot_id)
        if storage is not None:
            objects = {str(item.get("path") or ""): item for item in storage}
        else:
            objects = {
                obj.path: {"path": obj.path, "size": obj.size, "sha256": obj.sha256}
                for obj in self.session.scalars(select(StorageObjectRow)).all()
            }
        issues: list[VerificationIssue] = []
        for entry in row.files:
            obj = objects.get(entry.path)
            if obj is None:
                issues.append(VerificationIssue("missing_object", entry.path, "file is absent from storage"))
                continue
            try:
                size = int(obj.get("size"))
            except (TypeError, ValueError):
                issues.append(VerificationIssue("invalid_size", entry.path, "storage size is missing or invalid"))
                continue
            if size != entry.size:
                issues.append(VerificationIssue("size_mismatch", entry.path, "manifest and storage sizes differ", str(entry.size), str(size)))
            actual = str(obj.get("sha256") or "").lower()
            if actual != entry.sha256:
                issues.append(VerificationIssue("checksum_mismatch", entry.path, "manifest and storage checksums differ", entry.sha256, actual))
        for path in sorted(set(objects) - {f.path for f in row.files}):
            issues.append(VerificationIssue("unexpected_object", path, "storage object is absent from manifest"))
        self._audit("verified", snapshot_id, f"issues={len(issues)}")
        self.session.commit()
        return issues

    def restore_plan(self, snapshot_id: str, paths: list[str] | None = None) -> RestorePlan:
        row = self._snapshot(snapshot_id)
        wanted = set(paths or [])
        selected = [f for f in row.files if not wanted or f.path in wanted]
        missing = wanted - {f.path for f in selected}
        if missing:
            raise ValueError(f"paths not in snapshot: {sorted(missing)}")
        files = tuple(RestoreFile(f.path, f.size, f.sha256) for f in selected)
        self._audit("restore_planned", snapshot_id, f"files={len(files)}")
        self.session.commit()
        return RestorePlan(snapshot_id=snapshot_id, files=files, total_bytes=sum(f.size for f in files))

    def get_snapshot(self, snapshot_id: str) -> dict:
        row = self._snapshot(snapshot_id)
        return {
            "snapshot_id": row.snapshot_id,
            "job_id": row.job_id,
            "created_at": row.created_at.isoformat(),
            "fingerprint": row.fingerprint,
            "files": [{"path": f.path, "size": f.size, "sha256": f.sha256} for f in row.files],
        }

    def audit(self) -> list[dict]:
        rows = self.session.scalars(select(AuditRow).order_by(AuditRow.id)).all()
        return [
            {"at": row.at.isoformat(), "action": row.action, "reference": row.reference, "detail": row.detail}
            for row in rows
        ]

    def ready(self) -> bool:
        self.session.execute(select(1))
        return True
