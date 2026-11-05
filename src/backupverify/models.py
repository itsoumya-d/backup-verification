from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    job_id: str
    created_at: datetime
    files: tuple[FileEntry, ...]

    def fingerprint(self) -> str:
        payload = [
            {"path": f.path, "size": f.size, "sha256": f.sha256} for f in sorted(self.files, key=lambda x: x.path)
        ]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class AuditEntry:
    at: datetime
    action: str
    reference: str
    detail: str


@dataclass
class DeadLetter:
    letter_id: str
    reference: str
    payload: dict[str, Any]
    errors: list[str]


@dataclass
class IngestSummary:
    received: int = 0
    created: int = 0
    unchanged: int = 0
    rejected: int = 0
    dead_letters: list[DeadLetter] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationIssue:
    kind: str
    path: str
    detail: str
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True)
class RestoreFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RestorePlan:
    snapshot_id: str
    files: tuple[RestoreFile, ...]
    total_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "total_bytes": self.total_bytes,
            "files": [f.__dict__ for f in self.files],
        }
