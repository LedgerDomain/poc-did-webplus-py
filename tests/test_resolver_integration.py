"""Integration tests for Full DID Resolver."""

import json

import pytest
import respx
import rfc8785
from httpx import Response

from did_webplus.resolver import (
    FullDIDResolver,
    ResolutionError,
    ResolutionResult,
    _validate_document,
)
from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash
from did_webplus.store import SQLiteDIDDocStore


def _make_root_doc_with_placeholder() -> dict:
    return {
        "id": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}",
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }


@respx.mock
@pytest.mark.asyncio
async def test_resolve_fetches_and_stores(store: SQLiteDIDDocStore) -> None:
    doc = _make_root_doc_with_placeholder()
    compute_self_hash(doc)
    did = doc["id"]
    root_hash = doc["selfHash"]
    url = f"https://example.com/{root_hash}/did-documents.jsonl"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    respx.get(url).mock(return_value=Response(200, text=jcs + "\n"))

    resolver = FullDIDResolver(store)
    result = await resolver.resolve(did)

    assert result.did_document == jcs
    assert result.did_document_metadata.version_id == 0
    assert result.did_resolution_metadata.fetched_updates_from_vdr is True


@pytest.mark.asyncio
async def test_resolve_offline_when_cached(store: SQLiteDIDDocStore) -> None:
    doc = _make_root_doc_with_placeholder()
    compute_self_hash(doc)
    did = doc["id"]
    jcs = rfc8785.dumps(doc).decode("utf-8")
    await store.add_did_documents([jcs], 0)

    resolver = FullDIDResolver(store)
    result = await resolver.resolve(did)

    assert result.did_document == jcs
    assert result.did_resolution_metadata.did_document_resolved_locally is True
    assert result.did_resolution_metadata.fetched_updates_from_vdr is False


@respx.mock
@pytest.mark.asyncio
async def test_resolve_by_version_id(store: SQLiteDIDDocStore) -> None:
    doc = _make_root_doc_with_placeholder()
    compute_self_hash(doc)
    did = doc["id"]
    root_hash = doc["selfHash"]
    url = f"https://example.com/{root_hash}/did-documents.jsonl"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    respx.get(url).mock(return_value=Response(200, text=jcs + "\n"))

    resolver = FullDIDResolver(store)
    result = await resolver.resolve(f"{did}?versionId=0")

    assert result.did_document == jcs
    assert result.did_document_metadata.version_id == 0


# --- Ledgerdomain fixture tests (require: uv run python scripts/fetch_ledgerdomain_fixtures.py --no-validate) ---


@pytest.mark.asyncio
async def test_resolve_from_ledgerdomain_fixture(
    store: SQLiteDIDDocStore, ledgerdomain_did_1: dict | None
) -> None:
    """Resolve DID from pre-fetched ledgerdomain fixture (no network)."""
    if ledgerdomain_did_1 is None:
        pytest.skip("Ledgerdomain fixtures not found; run fetch_ledgerdomain_fixtures.py")

    lines = ledgerdomain_did_1["jsonl_path"].read_text().strip().split("\n")
    lines = [ln for ln in lines if ln.strip()]
    await store.add_did_documents(lines, 0)

    resolver = FullDIDResolver(store)
    did = ledgerdomain_did_1["did"]
    result = await resolver.resolve(did)

    assert result.did_document
    assert result.did_document_metadata.version_id is not None
    assert result.did_resolution_metadata.did_document_resolved_locally is True
    assert result.did_resolution_metadata.fetched_updates_from_vdr is False

    # Latest doc should be version 2 (deactivated)
    doc = json.loads(result.did_document)
    assert doc["versionId"] == 2
    assert doc.get("updateRules") == {}


@pytest.mark.asyncio
async def test_resolve_ledgerdomain_with_query_params(
    store: SQLiteDIDDocStore, ledgerdomain_did_1: dict | None
) -> None:
    """Resolve ledgerdomain DID with ?versionId=0 and ?selfHash=..."""
    if ledgerdomain_did_1 is None:
        pytest.skip("Ledgerdomain fixtures not found; run fetch_ledgerdomain_fixtures.py")

    lines = ledgerdomain_did_1["jsonl_path"].read_text().strip().split("\n")
    lines = [ln for ln in lines if ln.strip()]
    await store.add_did_documents(lines, 0)

    resolver = FullDIDResolver(store)
    did = ledgerdomain_did_1["did"]
    root_hash = ledgerdomain_did_1["root_self_hash"]

    result_v0 = await resolver.resolve(f"{did}?versionId=0")
    assert result_v0.did_document_metadata.version_id == 0
    doc_v0 = json.loads(result_v0.did_document)
    assert doc_v0["selfHash"] == root_hash

    result_sh = await resolver.resolve(f"{did}?selfHash={root_hash}")
    assert result_sh.did_document == result_v0.did_document


@pytest.mark.asyncio
async def test_resolve_or_result_returns_failed_on_error(
    store: SQLiteDIDDocStore,
) -> None:
    """resolve_or_result returns failed result instead of raising."""
    resolver = FullDIDResolver(store)
    result = await resolver.resolve_or_result(
        "did:webplus:example.com:nonexistent123",
        no_fetch=True,
    )
    assert result.did_resolution_metadata.error is not None
    assert result.did_document == ""
    assert "not found" in result.did_resolution_metadata.error.lower()


def test_resolution_result_failed_to_dict() -> None:
    """ResolutionResult.failed returns W3C-style dict with null didDocument."""
    result = ResolutionResult.failed("did:webplus:example.com:x", "error message")
    d = result.to_dict()
    assert d["didDocument"] is None
    assert d["didResolutionMetadata"]["error"] == "error message"




@pytest.mark.asyncio
async def test_ledgerdomain_fixture_chain_validation(
    ledgerdomain_fixtures: list[dict],
) -> None:
    """Validate that our _validate_document accepts each ledgerdomain fixture."""
    for entry in ledgerdomain_fixtures:
        lines = entry["jsonl_path"].read_text().strip().split("\n")
        lines = [ln for ln in lines if ln.strip()]
        prev_doc = None
        for line in lines:
            doc_dict = json.loads(line)
            _validate_document(line, doc_dict, prev_doc)
            prev_doc = doc_dict
