# backup-verification

[![ci](https://github.com/itsoumya-d/backup-verification/actions/workflows/ci.yml/badge.svg)](https://github.com/itsoumya-d/backup-verification/actions/workflows/ci.yml)

A production-oriented backup verification service: snapshot manifests, SHA-256
checksum verification against storage, restore planning, persisted audit events
and role-based API access.

## What it does

- Validates snapshot manifests: required IDs, unique paths, non-negative sizes
  and 64-character SHA-256 checksums.
- Idempotent snapshot ingestion; a changed manifest under the same snapshot ID
  is rejected with `409`.
- Registers storage objects and verifies snapshots against them: missing
  objects, size mismatches, checksum mismatches and unexpected objects.
- Builds restore plans for selected paths with total bytes and checksums.
- Persists snapshots, files, storage objects, dead letters and audit events in
  a real SQL database.
- Enforces role-based API keys (`viewer`, `operator`, `admin`).

This is a real service implementation, not a UI demo. It does **not** claim
production Comet Backup or storage-provider experience; live backup agents,
storage gateways and cloud providers are out of scope.

## API

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness |
| GET | `/ready` | none | Database readiness |
| POST | `/snapshots` | operator | Ingest a snapshot manifest |
| GET | `/snapshots/{id}` | viewer | Read a snapshot |
| POST | `/storage/objects` | operator | Register storage objects |
| POST | `/snapshots/{id}/verify` | operator | Verify against stored or supplied storage |
| POST | `/snapshots/{id}/restore-plan` | operator | Build a restore plan |
| GET | `/audit` | admin | Read the audit trail |

Send `X-API-Key: <key>` on every protected request.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export API_KEYS='{"dev-admin":"admin","dev-operator":"operator","dev-viewer":"viewer"}'
alembic upgrade head
uvicorn backupverify.api:app --reload
```

Then open `http://127.0.0.1:8000/docs`.

## Run with Docker + Postgres

```bash
docker compose up --build
```

The compose file runs `alembic upgrade head` before starting the API. Replace
the example API keys before exposing the service.

## Tests

```bash
pytest
```

The suite covers manifest validation, idempotency, conflicts, storage
registration, verification issues, restore plans, audit persistence, API auth
and RBAC.

## Deployment note

The service is container-ready and has a migration path. A public live URL is
not committed because it requires owner-controlled cloud credentials and a
managed Postgres instance; do not treat a local URL as a production deployment.

## License

MIT
