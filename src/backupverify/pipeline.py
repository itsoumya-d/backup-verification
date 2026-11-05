from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import AuditEntry, DeadLetter, FileEntry, IngestSummary, RestoreFile, RestorePlan, Snapshot, VerificationIssue

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BackupVerifier:
    def __init__(self) -> None:
        self.snapshots: dict[str, Snapshot] = {}
        self.dead_letters: list[DeadLetter] = []
        self.audit: list[AuditEntry] = []

    def _record(self, action: str, reference: str, detail: str) -> None:
        self.audit.append(AuditEntry(datetime.now(timezone.utc), action, reference, detail))

    def ingest(self, payload: dict[str, Any]) -> IngestSummary:
        summary = IngestSummary(received=1)
        reference = str(payload.get("snapshot_id") or "")
        try:
            snapshot = self._normalize(payload)
            existing = self.snapshots.get(snapshot.snapshot_id)
            if existing is None:
                self.snapshots[snapshot.snapshot_id] = snapshot
                summary.created = 1
                action = "created"
            elif existing.fingerprint() != snapshot.fingerprint():
                raise ValueError("snapshot already exists with different files")
            else:
                summary.unchanged = 1
                action = "unchanged"
            self._record(action, snapshot.snapshot_id, f"files={len(snapshot.files)}")
        except ValueError as exc:
            summary.rejected = 1
            letter = DeadLetter(uuid.uuid4().hex[:12], reference, dict(payload), [str(exc)])
            self.dead_letters.append(letter)
            summary.dead_letters.append(letter)
            self._record("rejected", reference, str(exc))
        summary.audit = list(self.audit)
        return summary

    def _normalize(self, payload: dict[str, Any]) -> Snapshot:
        snapshot_id = str(payload.get("snapshot_id") or "").strip()
        job_id = str(payload.get("job_id") or "").strip()
        if not snapshot_id:
            raise ValueError("snapshot_id is required")
        if not job_id:
            raise ValueError("job_id is required")
        raw_files = payload.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueError("snapshot must contain at least one file")
        files: list[FileEntry] = []
        seen: set[str] = set()
        for raw in raw_files:
            path = str(raw.get("path") or "").strip()
            if not path:
                raise ValueError("file path is required")
            if path in seen:
                raise ValueError(f"duplicate file path: {path}")
            seen.add(path)
            try:
                size = int(raw.get("size"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid size for {path}") from exc
            if size < 0:
                raise ValueError(f"negative size for {path}")
            digest = str(raw.get("sha256") or "").strip().lower()
            if not SHA256_RE.fullmatch(digest):
                raise ValueError(f"invalid sha256 for {path}")
            files.append(FileEntry(path=path, size=size, sha256=digest))
        created_raw = payload.get("created_at")
        try:
            created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00")) if created_raw else datetime.now(timezone.utc)
        except ValueError as exc:
            raise ValueError("invalid created_at") from exc
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return Snapshot(snapshot_id=snapshot_id, job_id=job_id, created_at=created, files=tuple(files))

    def verify(self, snapshot_id: str, storage: list[dict[str, Any]]) -> list[VerificationIssue]:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"unknown snapshot: {snapshot_id}")
        objects = {str(item.get("path") or ""): item for item in storage}
        issues: list[VerificationIssue] = []
        for entry in snapshot.files:
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
                issues.append(
                    VerificationIssue("size_mismatch", entry.path, "manifest and storage sizes differ", str(entry.size), str(size))
                )
            actual = str(obj.get("sha256") or "").lower()
            if actual != entry.sha256:
                issues.append(
                    VerificationIssue("checksum_mismatch", entry.path, "manifest and storage checksums differ", entry.sha256, actual)
                )
        for path in sorted(set(objects) - {f.path for f in snapshot.files}):
            issues.append(VerificationIssue("unexpected_object", path, "storage object is absent from manifest"))
        self._record("verified", snapshot_id, f"issues={len(issues)}")
        return issues

    def restore_plan(self, snapshot_id: str, paths: list[str] | None = None) -> RestorePlan:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"unknown snapshot: {snapshot_id}")
        wanted = set(paths or [])
        selected = [f for f in snapshot.files if not wanted or f.path in wanted]
        missing = wanted - {f.path for f in selected}
        if missing:
            raise ValueError(f"paths not in snapshot: {sorted(missing)}")
        files = tuple(RestoreFile(f.path, f.size, f.sha256) for f in selected)
        self._record("restore_planned", snapshot_id, f"files={len(files)}")
        return RestorePlan(snapshot_id=snapshot_id, files=files, total_bytes=sum(f.size for f in files))
