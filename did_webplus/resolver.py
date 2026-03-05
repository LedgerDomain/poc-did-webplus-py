"""Full DID Resolver for did:webplus."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from did_webplus.did import parse_did, parse_did_with_query

logger = logging.getLogger(__name__)
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

    @classmethod
    def failed(cls, did: str, error: str) -> ResolutionResult:
        """
        Create a failed resolution result per W3C DID Resolution.

        Use when resolution fails; didDocument is empty and error is in metadata.
        """
        return cls(
            did_document="",
            did_document_metadata=DIDDocumentMetadata(),
            did_resolution_metadata=DIDResolutionMetadata(error=error),
        )

    def to_dict(self) -> dict:
        """
        Return W3C-style resolution result with camelCase keys.

        Returns dict with didResolutionMetadata, didDocument, didDocumentMetadata
        for interoperability (e.g., HTTP binding, Universal Resolver).
        """
        return {
            "didResolutionMetadata": {
                "contentType": self.did_resolution_metadata.content_type,
                "error": self.did_resolution_metadata.error,
                "fetchedUpdatesFromVdr": self.did_resolution_metadata.fetched_updates_from_vdr,
                "didDocumentResolvedLocally": self.did_resolution_metadata.did_document_resolved_locally,
                "didDocumentMetadataResolvedLocally": self.did_resolution_metadata.did_document_metadata_resolved_locally,
            },
            "didDocument": self.did_document if self.did_document else None,
            "didDocumentMetadata": {
                k: v
                for k, v in {
                    "created": self.did_document_metadata.created,
                    "updated": self.did_document_metadata.updated,
                    "versionId": self.did_document_metadata.version_id,
                    "nextUpdate": self.did_document_metadata.next_update,
                    "deactivated": self.did_document_metadata.deactivated,
                }.items()
                if v is not None
            },
        }


class FullDIDResolver:
    """
    Full DID Resolver: fetches, verifies, and stores DID documents.

    Supports optional VDG for fetching.
    """

    def __init__(
        self,
        store: DIDDocStore,
        vdg_base_url: str | None = None,
        http_scheme_overrides: dict[str, str] | None = None,
    ) -> None:
        self._store = store
        self._vdg_base_url = vdg_base_url
        self._http_scheme_overrides = http_scheme_overrides or {}

    async def resolve(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
    ) -> ResolutionResult:
        """
        Resolve a DID (with optional ?selfHash=...&versionId=...).

        Returns the DID document and metadata.

        Args:
            did_query: DID URL, optionally with ?selfHash=...&versionId=...
            no_fetch: If True, resolve only from local store; fail if not cached.
        """
        parsed = parse_did_with_query(did_query)
        did = parsed.did
        query_self_hash = parsed.query_self_hash
        query_version_id = parsed.query_version_id

        logger.debug(
            "resolver: resolve did=%s query_self_hash=%s query_version_id=%s",
            did,
            query_self_hash,
            query_version_id,
        )

        fetched_from_vdr = False
        resolved_locally = False
        metadata_resolved_locally = False

        record: DIDDocRecord | None = None

        if query_self_hash or query_version_id is not None:
            # Specific version/selfHash: check store first, fetch only if not found
            if query_self_hash:
                record = await self._store.get_by_self_hash(did, query_self_hash)
            else:
                record = await self._store.get_by_version_id(did, query_version_id)

            if record is not None:
                logger.debug(
                    "resolver: found in store did=%s versionId=%s selfHash=%s",
                    did,
                    record.version_id,
                    record.self_hash,
                )
                resolved_locally = True
                metadata_resolved_locally = True
            elif no_fetch:
                raise ResolutionError(
                    f"DID not found in local store (offline mode): {did}"
                )
            else:
                logger.debug("resolver: fetching did=%s vdg=%s", did, self._vdg_base_url)
                await self._fetch_and_store(did)
                fetched_from_vdr = True
                if query_self_hash:
                    record = await self._store.get_by_self_hash(did, query_self_hash)
                else:
                    record = await self._store.get_by_version_id(did, query_version_id)
                if record is None:
                    logger.error(
                        "resolver: resolution failed did=%s (no record after fetch)", did
                    )
                    raise ResolutionError(f"DID resolution failed for {did}")
        else:
            # Latest: always fetch from VDR first to sync updates (unless no_fetch)
            if not no_fetch:
                logger.debug("resolver: fetching did=%s vdg=%s", did, self._vdg_base_url)
                await self._fetch_and_store(did)
                fetched_from_vdr = True
            record = await self._store.get_latest(did)
            if record is not None:
                resolved_locally = not fetched_from_vdr
                metadata_resolved_locally = not fetched_from_vdr
                logger.debug(
                    "resolver: found in store did=%s versionId=%s selfHash=%s",
                    did,
                    record.version_id,
                    record.self_hash,
                )
            elif no_fetch:
                raise ResolutionError(
                    f"DID not found in local store (offline mode): {did}"
                )
            else:
                logger.error(
                    "resolver: resolution failed did=%s (no record after fetch)", did
                )
                raise ResolutionError(f"DID resolution failed for {did}")

        logger.debug(
            "resolver: resolved did=%s versionId=%s",
            did,
            record.version_id,
        )
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

    def resolve_sync(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
    ) -> ResolutionResult:
        """
        Synchronous wrapper for resolve().

        Runs the async resolve in a new event loop. Use this when calling
        from synchronous code (scripts, non-async apps).
        """
        return asyncio.run(self.resolve(did_query, no_fetch=no_fetch))

    async def resolve_or_result(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
    ) -> ResolutionResult:
        """
        Resolve a DID, returning a failed result instead of raising.

        On success, returns ResolutionResult with did_document.
        On failure, returns ResolutionResult.failed() with error in metadata.
        Use for W3C-aligned output where callers expect a result object.
        """
        try:
            return await self.resolve(did_query, no_fetch=no_fetch)
        except ResolutionError as e:
            parsed = parse_did_with_query(did_query)
            return ResolutionResult.failed(parsed.did, str(e))

    def resolve_or_result_sync(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
    ) -> ResolutionResult:
        """Synchronous wrapper for resolve_or_result()."""
        return asyncio.run(self.resolve_or_result(did_query, no_fetch=no_fetch))

    async def _fetch_and_store(self, did: str) -> None:
        """Fetch microledger from VDR/VDG, validate, and store."""
        latest = await self._store.get_latest(did)
        known_length = (
            latest.did_documents_jsonl_octet_length
            if latest else 0
        )

        logger.debug(
            "resolver: _fetch_and_store did=%s known_length=%d",
            did,
            known_length,
        )
        content = await fetch_did_documents_jsonl(
            did,
            known_octet_length=known_length,
            vdg_base_url=self._vdg_base_url,
            http_scheme_overrides=self._http_scheme_overrides or None,
        )
        content = content.strip()
        if not content:
            logger.debug("resolver: _fetch_and_store did=%s no new content", did)
            return

        lines = [ln for ln in content.split("\n") if ln.strip()]
        if not lines:
            return

        logger.debug(
            "resolver: _fetch_and_store did=%s received %d lines",
            did,
            len(lines),
        )
        prev_doc = None
        if latest:
            prev_doc = json.loads(latest.did_document_jcs)

        for line in lines:
            line = line.strip()
            if not line:
                continue
            doc_dict = json.loads(line)
            logger.debug(
                "resolver: validating doc did=%s versionId=%s selfHash=%s",
                doc_dict.get("id"),
                doc_dict.get("versionId"),
                doc_dict.get("selfHash"),
            )
            _validate_document(line, doc_dict, prev_doc)
            # DID fork detection: same (did, version_id) but different selfHash
            existing = await self._store.get_by_version_id(
                doc_dict["id"], doc_dict["versionId"]
            )
            if existing and existing.self_hash != doc_dict["selfHash"]:
                raise ResolutionError(
                    f"DID fork detected: versionId {doc_dict['versionId']} has "
                    f"conflicting selfHash (stored: {existing.self_hash!r}, "
                    f"fetched: {doc_dict['selfHash']!r})"
                )
            prev_doc = doc_dict

        logger.info(
            "resolver: storing %d docs for did=%s",
            len(lines),
            did,
        )
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
