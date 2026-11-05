from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class SnapshotRow(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    job_id: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    files: Mapped[list["SnapshotFileRow"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class SnapshotFileRow(Base):
    __tablename__ = "snapshot_files"
    __table_args__ = (UniqueConstraint("snapshot_pk", "path", name="uq_snapshot_file_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_pk: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(2048))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[SnapshotRow] = relationship(back_populates="files")


class StorageObjectRow(Base):
    __tablename__ = "storage_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    reference: Mapped[str] = mapped_column(String(120), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")


class DeadLetterRow(Base):
    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[str] = mapped_column(Text)
    errors: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
