from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .models import FileEntry, Snapshot

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_snapshot(payload: dict[str, Any]) -> Snapshot:
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
