"""Targeted tests for locality-plan-driven resolver orchestration."""

from __future__ import annotations

import json

import pytest
import respx
import rfc8785
from httpx import Response

from did_webplus.resolution import (
    INVALID_DID,
    INVALID_DID_DOCUMENT,
    INVALID_DID_URL,
    LOCAL_RESOLUTION_NOT_POSSIBLE,
    NOT_FOUND,
    ResolutionOptions,
    VDR_FETCH_FAILED,
)
from did_webplus.resolver import FullDIDResolver
from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash
from did_webplus.store import SQLiteDIDDocStore


def _make_root_doc(*, deactivated: bool = True) -> dict:
    return {
        "id": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}",
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        # Empty updateRules => deactivated tombstone; non-empty keeps tip active.
        "updateRules": {} if deactivated else {"threshold": 1, "updateKey": []},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }


async def _seed(store: SQLiteDIDDocStore, doc: dict) -> tuple[str, str]:
    compute_self_hash(doc)
    jcs = rfc8785.dumps(doc).decode("utf-8")
    await store.add_did_documents([jcs], 0)
    return doc["id"], jcs


@pytest.mark.asyncio
async def test_no_fetch_alias_for_local_resolution_only(
    store: SQLiteDIDDocStore,
) -> None:
    doc = _make_root_doc(deactivated=True)
    did, jcs = await _seed(store, doc)
    resolver = FullDIDResolver(store)

    via_flag = await resolver.resolve(did, no_fetch=True)
    via_opts = await resolver.resolve(
        did, options=ResolutionOptions(local_resolution_only=True)
    )

    assert via_flag.did_document == jcs
    assert via_opts.did_document == jcs
    assert via_flag.did_resolution_metadata["fetchedUpdatesFromVDR"] is False
    assert via_opts.did_resolution_metadata["fetchedUpdatesFromVDR"] is False


@pytest.mark.asyncio
async def test_version_query_resolves_locally_without_fetch(
    store: SQLiteDIDDocStore,
) -> None:
    doc = _make_root_doc(deactivated=True)
    did, jcs = await _seed(store, doc)
    resolver = FullDIDResolver(store)

    # If the resolver tried to fetch, respx would fail (no route).
    result = await resolver.resolve(f"{did}?versionId=0")
    assert result.did_document == jcs
    assert result.did_resolution_metadata["didDocumentResolvedLocally"] is True
    assert result.did_resolution_metadata["didDocumentMetadataResolvedLocally"] is True
    assert result.did_resolution_metadata["fetchedUpdatesFromVDR"] is False


@pytest.mark.asyncio
async def test_query_conflict_fails_without_fetch(
    store: SQLiteDIDDocStore,
) -> None:
    doc = _make_root_doc(deactivated=True)
    did, _jcs = await _seed(store, doc)
    resolver = FullDIDResolver(store)

    result = await resolver.resolve_or_result(
        f"{did}?selfHash={doc['selfHash']}&versionId=1"
    )
    assert result.did_document is None
    assert result.did_resolution_metadata["error"]["type"] == INVALID_DID_URL
    assert result.did_resolution_metadata["fetchedUpdatesFromVDR"] is False
    assert result.did_resolution_metadata["didDocumentResolvedLocally"] is False


@pytest.mark.asyncio
async def test_known_absence_after_deactivation_no_fetch(
    store: SQLiteDIDDocStore,
) -> None:
    doc = _make_root_doc(deactivated=True)
    did, _jcs = await _seed(store, doc)
    resolver = FullDIDResolver(store)

    result = await resolver.resolve_or_result(f"{did}?versionId=99")
    assert result.did_document is None
    assert result.did_resolution_metadata["error"]["type"] == NOT_FOUND
    assert result.did_resolution_metadata["fetchedUpdatesFromVDR"] is False
    assert result.did_resolution_metadata["didDocumentResolvedLocally"] is False


@respx.mock
@pytest.mark.asyncio
async def test_metadata_forced_fetch_failure_preserves_doc_locality(
    store: SQLiteDIDDocStore,
) -> None:
    """Document local but requestNext at active tip forces fetch; failure keeps plan booleans."""
    doc = _make_root_doc(deactivated=False)
    # Non-empty updateRules without real keys still marks tip active for locality.
    # Avoid proof verification by never successfully fetching; seed only.
    compute_self_hash(doc)
    # updateRules non-empty means not deactivated; but verify_proofs is only on fetch.
    jcs = rfc8785.dumps(doc).decode("utf-8")
    await store.add_did_documents([jcs], 0)
    did = doc["id"]
    root_hash = doc["selfHash"]

    # Force HTTP so the client actually issues a request when a local prefix
    # already exists (HTTPS currently short-circuits Range fetches).
    url = f"http://example.com/{root_hash}/did-documents.jsonl"
    respx.get(url).mock(return_value=Response(500, text="boom"))

    resolver = FullDIDResolver(
        store, http_scheme_overrides={"example.com": "http"}
    )
    result = await resolver.resolve_or_result(
        f"{did}?versionId=0",
        options=ResolutionOptions(request_next=True),
    )
    assert result.did_document is None
    assert result.did_resolution_metadata["error"]["type"] == VDR_FETCH_FAILED
    # Document was local; next metadata was not → plan froze these before fetch.
    assert result.did_resolution_metadata["didDocumentResolvedLocally"] is True
    assert result.did_resolution_metadata["didDocumentMetadataResolvedLocally"] is False
    assert result.did_resolution_metadata["fetchedUpdatesFromVDR"] is True


@respx.mock
@pytest.mark.asyncio
async def test_fetched_document_validation_failure(
    store: SQLiteDIDDocStore,
) -> None:
    did = "did:webplus:example.com:uFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    url = (
        "https://example.com/uFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/"
        "did-documents.jsonl"
    )
    # Valid JSON but not a valid self-hashed DID document.
    bad = json.dumps({"id": did, "versionId": 0, "selfHash": "nope"})
    respx.get(url).mock(return_value=Response(200, text=bad + "\n"))

    resolver = FullDIDResolver(store)
    result = await resolver.resolve_or_result(f"{did}?versionId=0")
    assert result.did_document is None
    assert result.did_resolution_metadata["error"]["type"] == INVALID_DID_DOCUMENT
    assert result.did_resolution_metadata["fetchedUpdatesFromVDR"] is True
    assert result.did_resolution_metadata["didDocumentResolvedLocally"] is False


@pytest.mark.asyncio
async def test_malformed_did_maps_to_invalid_did(
    store: SQLiteDIDDocStore,
) -> None:
    resolver = FullDIDResolver(store)
    result = await resolver.resolve_or_result("did:web:example.com:abc", no_fetch=True)
    assert result.did_document is None
    assert result.did_resolution_metadata["error"]["type"] == INVALID_DID


@pytest.mark.asyncio
async def test_malformed_query_maps_to_invalid_did_url(
    store: SQLiteDIDDocStore,
) -> None:
    resolver = FullDIDResolver(store)
    result = await resolver.resolve_or_result(
        "did:webplus:example.com:uFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "?versionId=not-an-int",
        no_fetch=True,
    )
    assert result.did_document is None
    assert result.did_resolution_metadata["error"]["type"] == INVALID_DID_URL


@pytest.mark.asyncio
async def test_local_only_impossibility(
    store: SQLiteDIDDocStore,
) -> None:
    resolver = FullDIDResolver(store)
    result = await resolver.resolve_or_result(
        "did:webplus:example.com:uFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        options=ResolutionOptions(local_resolution_only=True),
    )
    assert result.did_document is None
    assert (
        result.did_resolution_metadata["error"]["type"] == LOCAL_RESOLUTION_NOT_POSSIBLE
    )
    assert result.did_resolution_metadata["fetchedUpdatesFromVDR"] is False
