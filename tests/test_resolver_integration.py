"""Integration tests for Full DID Resolver."""

import json

import pytest
import respx
import rfc8785
from httpx import Response

from did_webplus.resolver import FullDIDResolver, ResolutionError
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
