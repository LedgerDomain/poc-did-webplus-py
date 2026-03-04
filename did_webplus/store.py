"""SQLite-backed DID document storage for did:webplus."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Protocol


@dataclass
class DIDDocRecord:
    """A stored DID document record."""

    self_hash: str
    did: str
    version_id: int
    valid_from: str
    did_documents_jsonl_octet_length: int
    did_document_jcs: str


class DIDDocStore(Protocol):
    """Protocol for DID document storage."""

    async def add_did_documents(
        self,
        did_document_jcs_list: list[str],
        prev_octet_length: int = 0,
    ) -> None: ...

    async def get_by_self_hash(self, did: str, self_hash: str) -> DIDDocRecord | None: ...

    async def get_by_version_id(self, did: str, version_id: int) -> DIDDocRecord | None: ...

    async def get_latest(self, did: str) -> DIDDocRecord | None: ...

    async def get_microledger_jsonl(self, did: str) -> str: ...

    async def get_microledger_octet_length(self, did: str) -> int: ...

    async def get_microledger_from_byte_offset(self, did: str, offset: int) -> str: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS did_document_records (
    self_hash TEXT NOT NULL PRIMARY KEY,
    did TEXT NOT NULL,
    version_id BIGINT NOT NULL,
    valid_from TEXT NOT NULL,
    did_documents_jsonl_octet_length BIGINT NOT NULL,
    did_document_jcs TEXT NOT NULL,
    UNIQUE(did, version_id),
    UNIQUE(did, valid_from),
    UNIQUE(did, did_documents_jsonl_octet_length)
);
"""


class SQLiteDIDDocStore:
    """SQLite-backed implementation of DID document storage."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._path), check_same_thread=False
            )
            self._conn.execute(_SCHEMA)
            self._conn.commit()
        return self._conn

    async def add_did_documents(
        self,
        did_document_jcs_list: list[str],
        prev_octet_length: int = 0,
    ) -> None:
        """Add DID documents to the store. Idempotent (ON CONFLICT DO NOTHING)."""
        await asyncio.to_thread(
            self._add_did_documents_sync, did_document_jcs_list, prev_octet_length
        )

    def _add_did_documents_sync(
        self,
        did_document_jcs_list: list[str],
        prev_octet_length: int,
    ) -> None:
        import json

        conn = self._get_conn()
        cursor = conn.cursor()
        for jcs in did_document_jcs_list:
            doc = json.loads(jcs)
            logger.debug(
                "store: add_did_documents did=%s versionId=%s selfHash=%s",
                doc.get("id"),
                doc.get("versionId"),
                doc.get("selfHash"),
            )
            self_hash = doc["selfHash"]
            did = doc["id"]
            version_id = doc["versionId"]
            valid_from = doc["validFrom"]
            prev_octet_length += len(jcs.encode("utf-8")) + 1
            cursor.execute(
                """
                INSERT INTO did_document_records
                (self_hash, did, version_id, valid_from, did_documents_jsonl_octet_length, did_document_jcs)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (self_hash) DO NOTHING
                """,
                (self_hash, did, version_id, valid_from, prev_octet_length, jcs),
            )
        conn.commit()

    async def get_by_self_hash(self, did: str, self_hash: str) -> DIDDocRecord | None:
        """Get a DID document by DID and selfHash."""
        return await asyncio.to_thread(
            self._get_by_self_hash_sync, did, self_hash
        )

    def _get_by_self_hash_sync(self, did: str, self_hash: str) -> DIDDocRecord | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT self_hash, did, version_id, valid_from, did_documents_jsonl_octet_length, did_document_jcs "
            "FROM did_document_records WHERE did = ? AND self_hash = ?",
            (did, self_hash),
        ).fetchone()
        if row is None:
            return None
        return DIDDocRecord(
            self_hash=row[0],
            did=row[1],
            version_id=row[2],
            valid_from=row[3],
            did_documents_jsonl_octet_length=row[4],
            did_document_jcs=row[5],
        )

    async def get_by_version_id(self, did: str, version_id: int) -> DIDDocRecord | None:
        return await asyncio.to_thread(
            self._get_by_version_id_sync, did, version_id
        )

    def _get_by_version_id_sync(self, did: str, version_id: int) -> DIDDocRecord | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT self_hash, did, version_id, valid_from, did_documents_jsonl_octet_length, did_document_jcs "
            "FROM did_document_records WHERE did = ? AND version_id = ?",
            (did, version_id),
        ).fetchone()
        if row is None:
            return None
        return DIDDocRecord(
            self_hash=row[0],
            did=row[1],
            version_id=row[2],
            valid_from=row[3],
            did_documents_jsonl_octet_length=row[4],
            did_document_jcs=row[5],
        )

    async def get_latest(self, did: str) -> DIDDocRecord | None:
        """Get the latest DID document for a DID."""
        return await asyncio.to_thread(self._get_latest_sync, did)

    def _get_latest_sync(self, did: str) -> DIDDocRecord | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT self_hash, did, version_id, valid_from, did_documents_jsonl_octet_length, did_document_jcs "
            "FROM did_document_records WHERE did = ? ORDER BY version_id DESC LIMIT 1",
            (did,),
        ).fetchone()
        if row is None:
            return None
        return DIDDocRecord(
            self_hash=row[0],
            did=row[1],
            version_id=row[2],
            valid_from=row[3],
            did_documents_jsonl_octet_length=row[4],
            did_document_jcs=row[5],
        )

    async def get_microledger_jsonl(self, did: str) -> str:
        """Return newline-delimited JCS documents in version order."""
        return await asyncio.to_thread(self._get_microledger_jsonl_sync, did)

    def _get_microledger_jsonl_sync(self, did: str) -> str:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT did_document_jcs FROM did_document_records WHERE did = ? ORDER BY version_id ASC",
            (did,),
        ).fetchall()
        return "\n".join(r[0] for r in rows) if rows else ""

    async def get_microledger_octet_length(self, did: str) -> int:
        """Return total octet length of did-documents.jsonl for this DID."""
        return await asyncio.to_thread(self._get_microledger_octet_length_sync, did)

    def _get_microledger_octet_length_sync(self, did: str) -> int:
        latest = self._get_latest_sync(did)
        return latest.did_documents_jsonl_octet_length if latest else 0

    async def get_microledger_from_byte_offset(self, did: str, offset: int) -> str:
        """Return microledger content from byte offset (for Range: bytes=N-)."""
        return await asyncio.to_thread(
            self._get_microledger_from_byte_offset_sync, did, offset
        )

    def _get_microledger_from_byte_offset_sync(self, did: str, offset: int) -> str:
        content = self._get_microledger_jsonl_sync(did)
        content_bytes = content.encode("utf-8")
        if offset >= len(content_bytes):
            return ""
        return content_bytes[offset:].decode("utf-8")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
