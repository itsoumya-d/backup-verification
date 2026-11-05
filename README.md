# backup-verification

[![ci](https://github.com/itsoumya-d/backup-verification/actions/workflows/ci.yml/badge.svg)](https://github.com/itsoumya-d/backup-verification/actions/workflows/ci.yml)

A small, tested reference for backup verification and restore planning:

- Validate backup snapshot manifests: required IDs, unique paths, sizes and
  SHA-256 checksums.
- Idempotent snapshot ingestion; a changed manifest under the same snapshot ID
  is rejected.
- Verify a snapshot against storage objects: missing objects, size mismatches,
  checksum mismatches and unexpected objects.
- Build a restore plan for selected paths with total bytes and checksums.
- Audit every ingest, verification and restore plan.
- FastAPI endpoints and a pytest suite.

This is a **reference implementation**, not a claim of production Comet Backup
or storage-provider experience. Live backup agents, storage gateways and cloud
providers are out of scope; the manifest, verification, restore and audit core
is tested.

## Run

```bash
uv venv --python 3.12
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn backupverify.api:app --reload
```

## License

MIT
