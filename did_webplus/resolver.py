"""Full DID Resolver for did:webplus."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, NoReturn

import httpx

from did_webplus.did import MalformedDIDError, parse_did, parse_did_with_query
from did_webplus.document import parse_did_document
from did_webplus.http_client import HTTPClientError, fetch_did_documents_jsonl
from did_webplus.resolution import (
    INTERNAL_ERROR,
    INVALID_DID,
    INVALID_DID_DOCUMENT,
    INVALID_DID_URL,
    NOT_FOUND,
    VDR_FETCH_FAILED,
    LocalDocumentRef,
    LocalityPlan,
    LocalPrefixSnapshot,
    ProblemDetails,
    ResolutionOptions,
    _known_absence,
    _query_conflict,
    build_did_document_metadata,
    build_failure_resolution_dict,
    build_success_resolution_dict,
    plan_locality,
)
from did_webplus.selfhash import (
    SelfHashError,
    verify_is_canonically_serialized,
    verify_self_hash,
)
from did_webplus.store import DIDDocRecord, DIDDocStore
from did_webplus.verification import VerificationError, verify_proofs

logger = logging.getLogger(__name__)


class ResolutionError(Exception):
    """DID resolution failed."""

    def __init__(
        self,
        message: str,
        *,
        problem: ProblemDetails | None = None,
        did_document_resolved_locally: bool = False,
        did_document_metadata_resolved_locally: bool = False,
        fetched_updates_from_vdr: bool = False,
    ) -> None:
        super().__init__(message)
        self.problem = problem
        self.did_document_resolved_locally = did_document_resolved_locally
        self.did_document_metadata_resolved_locally = (
            did_document_metadata_resolved_locally
        )
        self.fetched_updates_from_vdr = fetched_updates_from_vdr

    def with_locality(
        self,
        *,
        did_document_resolved_locally: bool,
        did_document_metadata_resolved_locally: bool,
        fetched_updates_from_vdr: bool,
    ) -> ResolutionError:
        """Return a copy of this error carrying the frozen locality booleans."""
        return ResolutionError(
            str(self),
            problem=self.problem,
            did_document_resolved_locally=did_document_resolved_locally,
            did_document_metadata_resolved_locally=(
                did_document_metadata_resolved_locally
            ),
            fetched_updates_from_vdr=fetched_updates_from_vdr,
        )


def _split_jsonl_records(
    content: str,
    *,
    after_archived_boundary: bool = False,
) -> list[str]:
    """
    Split a JSONL body into record lines with strict structural rules.

    - CR (\\r) is rejected (including CRLF line endings).
    - Blank lines are rejected.
    - A single trailing newline after the last record is allowed and dropped.
    - Lines are not stripped (wire bytes must match JCS exactly).
    - When ``after_archived_boundary`` is true (incremental Range suffix),
      consume exactly one leading separator newline at the archived-document
      boundary. A suffix of only that newline (trailing-NL source file with no
      new documents) yields no records. Missing or duplicated separators fail.
    """
    if "\r" in content:
        raise ResolutionError(
            "malformed-jsonl-line: CR/CRLF not allowed",
            problem=ProblemDetails.make(
                INVALID_DID_DOCUMENT,
                "malformed-jsonl-line: CR/CRLF not allowed",
            ),
        )
    if after_archived_boundary:
        if not content:
            return []
        if not content.startswith("\n"):
            raise ResolutionError(
                "malformed-jsonl-line: expected separator newline at "
                "archived-document boundary",
                problem=ProblemDetails.make(
                    INVALID_DID_DOCUMENT,
                    "malformed-jsonl-line: expected separator newline at "
                    "archived-document boundary",
                ),
            )
        content = content[1:]
        if not content:
            # Suffix was only the trailing newline of the source file.
            return []
    if content.endswith("\n"):
        content = content[:-1]
    if not content:
        return []
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line == "":
            raise ResolutionError(
                f"malformed-jsonl-line: blank line at index {i}",
                problem=ProblemDetails.make(
                    INVALID_DID_DOCUMENT,
                    f"malformed-jsonl-line: blank line at index {i}",
                ),
            )
    return lines


def _fail_with_plan(
    plan: LocalityPlan,
    message: str,
    problem: ProblemDetails,
) -> NoReturn:
    """Raise ResolutionError carrying the frozen locality plan booleans."""
    raise ResolutionError(
        message,
        problem=problem,
        did_document_resolved_locally=plan.did_document_resolved_locally,
        did_document_metadata_resolved_locally=(
            plan.did_document_metadata_resolved_locally
        ),
        fetched_updates_from_vdr=plan.fetched_updates_from_vdr,
    )


def _parse_failure(did_query: str, exc: MalformedDIDError) -> ResolutionError:
    """Map MalformedDIDError to INVALID_DID or INVALID_DID_URL."""
    did_part = did_query.split("#", 1)[0].split("?", 1)[0]
    try:
        parse_did(did_part)
    except MalformedDIDError:
        return ResolutionError(
            str(exc),
            problem=ProblemDetails.make(INVALID_DID, str(exc)),
        )
    return ResolutionError(
        str(exc),
        problem=ProblemDetails.make(INVALID_DID_URL, str(exc)),
    )


class ResolutionResult:
    """
    Result of DID resolution with exact wire-shaped metadata dictionaries.

    On failure: ``did_document`` is ``None``, ``did_document_metadata`` is
    ``{}``, and ``did_resolution_metadata`` carries an RFC 9457 ``error`` plus
    the three locality booleans.
    """

    def __init__(
        self,
        *,
        did_document: str | None,
        did_document_metadata: dict[str, Any],
        did_resolution_metadata: dict[str, Any],
    ) -> None:
        self.did_document = did_document
        self.did_document_metadata = did_document_metadata
        self.did_resolution_metadata = did_resolution_metadata

    @classmethod
    def failed(
        cls,
        error: ProblemDetails | str,
        *,
        did_document_resolved_locally: bool = False,
        did_document_metadata_resolved_locally: bool = False,
        fetched_updates_from_vdr: bool = False,
    ) -> ResolutionResult:
        """
        Create a failed resolution result per W3C DID Resolution / RFC 9457.

        ``didDocument`` is null, ``didDocumentMetadata`` is ``{}``, and
        resolution metadata includes ``error`` plus the three booleans.
        """
        if isinstance(error, str):
            problem = ProblemDetails.make(NOT_FOUND, error)
        else:
            problem = error
        wire = build_failure_resolution_dict(
            problem,
            did_document_resolved_locally=did_document_resolved_locally,
            did_document_metadata_resolved_locally=did_document_metadata_resolved_locally,
            fetched_updates_from_vdr=fetched_updates_from_vdr,
        )
        return cls(
            did_document=None,
            did_document_metadata=wire["didDocumentMetadata"],
            did_resolution_metadata=wire["didResolutionMetadata"],
        )

    @classmethod
    def success(
        cls,
        *,
        did_document: str,
        did_document_metadata: dict[str, Any],
        did_document_resolved_locally: bool,
        did_document_metadata_resolved_locally: bool,
        fetched_updates_from_vdr: bool,
    ) -> ResolutionResult:
        """Create a successful representation resolution result."""
        wire = build_success_resolution_dict(
            did_document=did_document,
            did_document_metadata=did_document_metadata,
            did_document_resolved_locally=did_document_resolved_locally,
            did_document_metadata_resolved_locally=did_document_metadata_resolved_locally,
            fetched_updates_from_vdr=fetched_updates_from_vdr,
        )
        return cls(
            did_document=wire["didDocument"],
            did_document_metadata=wire["didDocumentMetadata"],
            did_resolution_metadata=wire["didResolutionMetadata"],
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Return W3C-style resolution result with camelCase keys.

        Keys: ``didResolutionMetadata``, ``didDocument``, ``didDocumentMetadata``.
        """
        return {
            "didResolutionMetadata": self.did_resolution_metadata,
            "didDocument": self.did_document,
            "didDocumentMetadata": self.did_document_metadata,
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
        options: ResolutionOptions | None = None,
    ) -> ResolutionResult:
        """
        Resolve a DID (with optional ?selfHash=...&versionId=...).

        Pipeline: parse -> local snapshot -> locality plan -> optional fetch
        (at most one) -> final selection -> metadata construction.

        Locality booleans are frozen by the pre-fetch plan and are not revised
        after data arrives.

        Args:
            did_query: DID URL, optionally with ?selfHash=...&versionId=...
            no_fetch: Compatibility alias for ``localResolutionOnly``.
            options: Resolution options; ``no_fetch`` OR's into
                ``local_resolution_only`` when true.
        """
        try:
            return await self._resolve_pipeline(
                did_query, no_fetch=no_fetch, options=options
            )
        except ResolutionError:
            raise
        except Exception as e:
            logger.exception("resolver: unexpected internal error for %s", did_query)
            raise ResolutionError(
                str(e),
                problem=ProblemDetails.make(INTERNAL_ERROR, str(e)),
            ) from e

    async def _resolve_pipeline(
        self,
        did_query: str,
        *,
        no_fetch: bool,
        options: ResolutionOptions | None,
    ) -> ResolutionResult:
        opts = ResolutionOptions.coalesce(options, no_fetch=no_fetch)

        try:
            parsed = parse_did_with_query(did_query)
            # parse_did_with_query currently skips structural checks when there
            # is no query string; validate the DID itself here.
            parse_did(parsed.did)
        except MalformedDIDError as e:
            raise _parse_failure(did_query, e) from e

        did = parsed.did
        query_self_hash = parsed.query_self_hash
        query_version_id = parsed.query_version_id

        logger.debug(
            "resolver: resolve did=%s query_self_hash=%s query_version_id=%s "
            "local_resolution_only=%s",
            did,
            query_self_hash,
            query_version_id,
            opts.local_resolution_only,
        )

        snapshot = await self._local_prefix_snapshot(did)
        plan = plan_locality(
            snapshot,
            query_self_hash=query_self_hash,
            query_version_id=query_version_id,
            options=opts,
        )

        if plan.early_failure is not None:
            _fail_with_plan(
                plan,
                plan.early_failure.detail,
                plan.early_failure,
            )

        if plan.should_fetch:
            logger.debug("resolver: fetching did=%s vdg=%s", did, self._vdg_base_url)
            try:
                await self._fetch_and_store(did)
            except ResolutionError as e:
                problem = e.problem or ProblemDetails.make(VDR_FETCH_FAILED, str(e))
                raise ResolutionError(
                    str(e),
                    problem=problem,
                    did_document_resolved_locally=plan.did_document_resolved_locally,
                    did_document_metadata_resolved_locally=(
                        plan.did_document_metadata_resolved_locally
                    ),
                    fetched_updates_from_vdr=plan.fetched_updates_from_vdr,
                ) from e

            # Re-check conflict / known absence on the updated local view.
            snapshot = await self._local_prefix_snapshot(did)
            if _query_conflict(snapshot, query_self_hash, query_version_id):
                _fail_with_plan(
                    plan,
                    "selfHash and versionId query parameters conflict",
                    ProblemDetails.make(
                        INVALID_DID_URL,
                        "selfHash and versionId query parameters conflict",
                    ),
                )
            if _known_absence(snapshot, query_self_hash, query_version_id):
                _fail_with_plan(
                    plan,
                    "requested DID document is known absent after deactivation",
                    ProblemDetails.make(
                        NOT_FOUND,
                        "requested DID document is known absent after deactivation",
                    ),
                )

        record = await self._select_record(
            did,
            query_self_hash=query_self_hash,
            query_version_id=query_version_id,
        )
        if record is None:
            logger.error(
                "resolver: resolution failed did=%s (no matching document)", did
            )
            if snapshot.is_empty:
                detail = f"DID resolution for {did_query} failed: empty microledger"
            else:
                detail = f"DID resolution for {did_query} failed"
            _fail_with_plan(
                plan,
                f"DID resolution failed for {did}",
                ProblemDetails.make(NOT_FOUND, detail),
            )

        logger.debug(
            "resolver: resolved did=%s versionId=%s",
            did,
            record.version_id,
        )
        doc = parse_did_document(record.did_document_jcs)

        root_valid_from: str | None = None
        if opts.request_create:
            if record.version_id == 0:
                root_valid_from = record.valid_from
            else:
                root = await self._store.get_by_version_id(did, 0)
                if root is None:
                    _fail_with_plan(
                        plan,
                        f"root DID document not available for {did}",
                        ProblemDetails.make(
                            NOT_FOUND,
                            f"DID resolution for {did_query} failed",
                        ),
                    )
                root_valid_from = root.valid_from

        next_valid_from: str | None = None
        next_version_id: int | None = None
        if opts.request_next:
            next_record = await self._store.get_by_version_id(did, doc.version_id + 1)
            if next_record is not None:
                next_valid_from = next_record.valid_from
                next_version_id = next_record.version_id

        latest_valid_from: str | None = None
        latest_version_id: int | None = None
        if opts.request_latest:
            latest = await self._store.get_latest(did)
            if latest is None:
                _fail_with_plan(
                    plan,
                    f"latest DID document not available for {did}",
                    ProblemDetails.make(
                        NOT_FOUND,
                        f"DID resolution for {did_query} failed",
                    ),
                )
            latest_valid_from = latest.valid_from
            latest_version_id = latest.version_id

        metadata = build_did_document_metadata(
            options=opts,
            version_id=record.version_id,
            valid_from=record.valid_from,
            is_root=doc.is_root_document(),
            root_valid_from=root_valid_from,
            next_valid_from=next_valid_from,
            next_version_id=next_version_id,
            latest_valid_from=latest_valid_from,
            latest_version_id=latest_version_id,
            deactivated=doc.is_deactivated(),
        )

        return ResolutionResult.success(
            did_document=record.did_document_jcs,
            did_document_metadata=metadata,
            did_document_resolved_locally=plan.did_document_resolved_locally,
            did_document_metadata_resolved_locally=(
                plan.did_document_metadata_resolved_locally
            ),
            fetched_updates_from_vdr=plan.fetched_updates_from_vdr,
        )

    def resolve_sync(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
        options: ResolutionOptions | None = None,
    ) -> ResolutionResult:
        """
        Synchronous wrapper for resolve().

        Runs the async resolve in a new event loop. Use this when calling
        from synchronous code (scripts, non-async apps).
        """
        return asyncio.run(
            self.resolve(did_query, no_fetch=no_fetch, options=options)
        )

    async def resolve_or_result(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
        options: ResolutionOptions | None = None,
    ) -> ResolutionResult:
        """
        Resolve a DID, returning a failed result instead of raising.

        On success, returns ResolutionResult with did_document.
        On failure, returns ResolutionResult.failed() with RFC 9457 error.
        Use for W3C-aligned output where callers expect a result object.
        """
        try:
            return await self.resolve(
                did_query, no_fetch=no_fetch, options=options
            )
        except ResolutionError as e:
            problem = (
                e.problem
                if e.problem is not None
                else ProblemDetails.make(NOT_FOUND, str(e))
            )
            return ResolutionResult.failed(
                problem,
                did_document_resolved_locally=e.did_document_resolved_locally,
                did_document_metadata_resolved_locally=(
                    e.did_document_metadata_resolved_locally
                ),
                fetched_updates_from_vdr=e.fetched_updates_from_vdr,
            )

    def resolve_or_result_sync(
        self,
        did_query: str,
        *,
        no_fetch: bool = False,
        options: ResolutionOptions | None = None,
    ) -> ResolutionResult:
        """Synchronous wrapper for resolve_or_result()."""
        return asyncio.run(
            self.resolve_or_result(
                did_query, no_fetch=no_fetch, options=options
            )
        )

    async def _local_prefix_snapshot(self, did: str) -> LocalPrefixSnapshot:
        """Build a contiguous verified local prefix snapshot for ``did``."""
        jsonl = await self._store.get_microledger_jsonl(did)
        if not jsonl:
            return LocalPrefixSnapshot()
        docs: list[LocalDocumentRef] = []
        for line in jsonl.split("\n"):
            if not line:
                continue
            doc = parse_did_document(line)
            docs.append(
                LocalDocumentRef(
                    version_id=doc.version_id,
                    self_hash=doc.self_hash,
                    deactivated=doc.is_deactivated(),
                )
            )
        return LocalPrefixSnapshot.from_documents(docs)

    async def _select_record(
        self,
        did: str,
        *,
        query_self_hash: str | None,
        query_version_id: int | None,
    ) -> DIDDocRecord | None:
        """Select the requested DID document record from the store."""
        if query_self_hash is not None and query_version_id is not None:
            by_hash = await self._store.get_by_self_hash(did, query_self_hash)
            by_version = await self._store.get_by_version_id(did, query_version_id)
            return by_hash if by_hash is not None else by_version
        if query_self_hash is not None:
            return await self._store.get_by_self_hash(did, query_self_hash)
        if query_version_id is not None:
            return await self._store.get_by_version_id(did, query_version_id)
        return await self._store.get_latest(did)

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
        try:
            content = await fetch_did_documents_jsonl(
                did,
                known_octet_length=known_length,
                vdg_base_url=self._vdg_base_url,
                http_scheme_overrides=self._http_scheme_overrides or None,
            )
        except HTTPClientError as e:
            raise ResolutionError(
                str(e),
                problem=ProblemDetails.make(VDR_FETCH_FAILED, str(e)),
            ) from e
        except httpx.HTTPError as e:
            raise ResolutionError(
                str(e),
                problem=ProblemDetails.make(VDR_FETCH_FAILED, str(e)),
            ) from e

        if not content:
            logger.debug("resolver: _fetch_and_store did=%s no new content", did)
            return

        # Validate the complete fetched suffix before writing any record/offset.
        lines = _split_jsonl_records(
            content,
            after_archived_boundary=known_length > 0,
        )
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
            try:
                doc_dict = json.loads(line)
            except json.JSONDecodeError as e:
                raise ResolutionError(
                    f"malformed-jsonl-line: invalid JSON: {e}",
                    problem=ProblemDetails.make(
                        INVALID_DID_DOCUMENT,
                        f"malformed-jsonl-line: invalid JSON: {e}",
                    ),
                ) from e
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
                msg = (
                    f"DID fork detected: versionId {doc_dict['versionId']} has "
                    f"conflicting selfHash (stored: {existing.self_hash!r}, "
                    f"fetched: {doc_dict['selfHash']!r})"
                )
                raise ResolutionError(
                    msg,
                    problem=ProblemDetails.make(INVALID_DID_DOCUMENT, msg),
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
    try:
        if "versionId" not in doc_dict or type(doc_dict["versionId"]) is not int:
            raise ResolutionError(
                f"versionId must be a JSON integer, got "
                f"{type(doc_dict.get('versionId')).__name__}",
                problem=ProblemDetails.make(
                    INVALID_DID_DOCUMENT,
                    f"versionId must be a JSON integer, got "
                    f"{type(doc_dict.get('versionId')).__name__}",
                ),
            )
        verify_is_canonically_serialized(doc_dict, jcs_str)
        verify_self_hash(jcs_str)
        doc = parse_did_document(jcs_str)
        prev = parse_did_document(json.dumps(prev_doc)) if prev_doc else None
        doc.verify_chain_constraints(prev)
        verify_proofs(doc_dict, prev_doc)
    except ResolutionError:
        raise
    except SelfHashError as e:
        raise ResolutionError(
            f"Self-hash verification failed: {e}",
            problem=ProblemDetails.make(
                INVALID_DID_DOCUMENT,
                f"Self-hash verification failed: {e}",
            ),
        ) from e
    except VerificationError as e:
        raise ResolutionError(
            f"Proof verification failed: {e}",
            problem=ProblemDetails.make(
                INVALID_DID_DOCUMENT,
                f"Proof verification failed: {e}",
            ),
        ) from e
    except ValueError as e:
        raise ResolutionError(
            f"Document validation failed: {e}",
            problem=ProblemDetails.make(
                INVALID_DID_DOCUMENT,
                f"Document validation failed: {e}",
            ),
        ) from e
