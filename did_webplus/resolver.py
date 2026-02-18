"""Full DID Resolver for did:webplus."""

from __future__ import annotations

import json
from dataclasses import dataclass

from did_webplus.did import parse_did, parse_did_with_query
from did_webplus.document import DIDDocument, parse_did_document
from did_webplus.http_client import fetch_did_documents_jsonl
from did_webplus.selfhash import verify_self_hash
from did_webplus.store import DIDDocRecord, DIDDocStore
from did_webplus.verification import VerificationError, verify_proofs


class ResolutionError(Exception):
    """DID resolution failed."""


@dataclass
class DIDDocumentMetadata:
    """Metadata about the resolved DID document."""

    created: str | None = None
    updated: str | None = None
    version_id: int | None = None
    next_update: str | None = None
    deactivated: bool | None = None


@dataclass
class DIDResolutionMetadata:
    """Metadata about the resolution process."""

    content_type: str = "application/did+json"
    error: str | None = None
    fetched_updates_from_vdr: bool = False
    did_document_resolved_locally: bool = False
    did_document_metadata_resolved_locally: bool = False


@dataclass
class ResolutionResult:
    """Result of DID resolution."""

    did_document: str
    did_document_metadata: DIDDocumentMetadata
    did_resolution_metadata: DIDResolutionMetadata


class FullDIDResolver:
    """
    Full DID Resolver: fetches, verifies, and stores DID documents.

    Supports optional VDG for fetching.
    """

    def __init__(
        self,
        store: DIDDocStore,
        vdg_base_url: str | None = None,
    ) -> None:
        self._store = store
        self._vdg_base_url = vdg_base_url

    async def resolve(self, did_query: str) -> ResolutionResult:
        """
        Resolve a DID (with optional ?selfHash=...&versionId=...).

        Returns the DID document and metadata.
        """
        parsed = parse_did_with_query(did_query)
        did = parsed.did
        query_self_hash = parsed.query_self_hash
        query_version_id = parsed.query_version_id

        fetched_from_vdr = False
        resolved_locally = False
        metadata_resolved_locally = False

        record: DIDDocRecord | None = None

        if query_self_hash:
            record = await self._store.get_by_self_hash(did, query_self_hash)
        elif query_version_id is not None:
            record = await self._store.get_by_version_id(did, query_version_id)
        else:
            record = await self._store.get_latest(did)

        if record is not None:
            resolved_locally = True
            metadata_resolved_locally = True
        else:
            await self._fetch_and_store(did)
            fetched_from_vdr = True
            if query_self_hash:
                record = await self._store.get_by_self_hash(did, query_self_hash)
            elif query_version_id is not None:
                record = await self._store.get_by_version_id(did, query_version_id)
            else:
                record = await self._store.get_latest(did)
            if record is None:
                raise ResolutionError(f"DID resolution failed for {did}")

        doc = parse_did_document(record.did_document_jcs)
        next_record = await self._store.get_by_version_id(did, doc.version_id + 1)

        metadata = DIDDocumentMetadata(
            created=record.valid_from if record.version_id == 0 else None,
            updated=record.valid_from,
            version_id=record.version_id,
            next_update=next_record.valid_from if next_record else None,
            deactivated=doc.is_deactivated(),
        )

        resolution_metadata = DIDResolutionMetadata(
            fetched_updates_from_vdr=fetched_from_vdr,
            did_document_resolved_locally=resolved_locally,
            did_document_metadata_resolved_locally=metadata_resolved_locally,
        )

        return ResolutionResult(
            did_document=record.did_document_jcs,
            did_document_metadata=metadata,
            did_resolution_metadata=resolution_metadata,
        )

    async def _fetch_and_store(self, did: str) -> None:
        """Fetch microledger from VDR/VDG, validate, and store."""
        latest = await self._store.get_latest(did)
        known_length = (
            latest.did_documents_jsonl_octet_length
            if latest else 0
        )

        content = await fetch_did_documents_jsonl(
            did,
            known_octet_length=known_length,
            vdg_base_url=self._vdg_base_url,
        )
        content = content.strip()
        if not content:
            return

        lines = [ln for ln in content.split("\n") if ln.strip()]
        if not lines:
            return

        prev_doc = None
        if latest:
            prev_doc = json.loads(latest.did_document_jcs)

        for line in lines:
            line = line.strip()
            if not line:
                continue
            doc_dict = json.loads(line)
            _validate_document(line, doc_dict, prev_doc)
            prev_doc = doc_dict

        await self._store.add_did_documents(lines, known_length)


def _validate_document(
    jcs_str: str,
    doc_dict: dict,
    prev_doc: dict | None,
) -> None:
    """Validate a single document (self-hash, chain, proofs) and raise if invalid."""
    verify_self_hash(jcs_str)
    doc = parse_did_document(jcs_str)
    prev = parse_did_document(json.dumps(prev_doc)) if prev_doc else None
    doc.verify_chain_constraints(prev)
    try:
        verify_proofs(doc_dict, prev_doc)
    except VerificationError as e:
        raise ResolutionError(f"Proof verification failed: {e}") from e
