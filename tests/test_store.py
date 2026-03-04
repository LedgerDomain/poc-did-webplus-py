"""Tests for SQLite DID document store."""

import json

import pytest

from did_webplus.store import DIDDocRecord, SQLiteDIDDocStore


@pytest.mark.asyncio
async def test_add_and_get_by_self_hash(store: SQLiteDIDDocStore) -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash1",
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
    jcs = json.dumps(doc, sort_keys=True)
    await store.add_did_documents([jcs], 0)
    record = await store.get_by_self_hash("did:webplus:example.com:abc", "Ehash1")
    assert record is not None
    assert record.self_hash == "Ehash1"
    assert record.version_id == 0
    assert record.did_documents_jsonl_octet_length == len(jcs) + 1


@pytest.mark.asyncio
async def test_add_and_get_by_version_id(store: SQLiteDIDDocStore) -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash1",
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
    jcs = json.dumps(doc, sort_keys=True)
    await store.add_did_documents([jcs], 0)
    record = await store.get_by_version_id("did:webplus:example.com:abc", 0)
    assert record is not None
    assert record.version_id == 0


@pytest.mark.asyncio
async def test_get_latest(store: SQLiteDIDDocStore) -> None:
    doc0 = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash0",
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
    doc1 = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash1",
        "prevDIDDocumentSelfHash": "Ehash0",
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 1,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    jcs0 = json.dumps(doc0, sort_keys=True)
    jcs1 = json.dumps(doc1, sort_keys=True)
    await store.add_did_documents([jcs0, jcs1], 0)
    record = await store.get_latest("did:webplus:example.com:abc")
    assert record is not None
    assert record.version_id == 1
    assert record.self_hash == "Ehash1"


@pytest.mark.asyncio
async def test_idempotent_add(store: SQLiteDIDDocStore) -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash1",
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
    jcs = json.dumps(doc, sort_keys=True)
    await store.add_did_documents([jcs], 0)
    await store.add_did_documents([jcs], 0)
    record = await store.get_by_self_hash("did:webplus:example.com:abc", "Ehash1")
    assert record is not None


@pytest.mark.asyncio
async def test_get_microledger_jsonl(store: SQLiteDIDDocStore) -> None:
    doc0 = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash0",
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
    doc1 = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash1",
        "prevDIDDocumentSelfHash": "Ehash0",
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 1,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    jcs0 = json.dumps(doc0, sort_keys=True)
    jcs1 = json.dumps(doc1, sort_keys=True)
    await store.add_did_documents([jcs0, jcs1], 0)
    jsonl = await store.get_microledger_jsonl("did:webplus:example.com:abc")
    assert jsonl == f"{jcs0}\n{jcs1}"
    assert await store.get_microledger_jsonl("did:webplus:example.com:nonexistent") == ""


@pytest.mark.asyncio
async def test_get_microledger_octet_length(store: SQLiteDIDDocStore) -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Ehash1",
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
    jcs = json.dumps(doc, sort_keys=True)
    await store.add_did_documents([jcs], 0)
    length = await store.get_microledger_octet_length("did:webplus:example.com:abc")
    assert length == len(jcs) + 1
    assert await store.get_microledger_octet_length("did:webplus:example.com:nonexistent") == 0


@pytest.mark.asyncio
async def test_get_microledger_from_byte_offset(store: SQLiteDIDDocStore) -> None:
    doc0 = {"id": "did:webplus:example.com:x", "selfHash": "H0", "validFrom": "2024-01-01T00:00:00.000Z", "versionId": 0, "updateRules": {}, "proofs": [], "verificationMethod": [], "authentication": [], "assertionMethod": [], "keyAgreement": [], "capabilityInvocation": [], "capabilityDelegation": []}
    doc1 = {"id": "did:webplus:example.com:x", "selfHash": "H1", "prevDIDDocumentSelfHash": "H0", "validFrom": "2024-01-02T00:00:00.000Z", "versionId": 1, "updateRules": {}, "proofs": [], "verificationMethod": [], "authentication": [], "assertionMethod": [], "keyAgreement": [], "capabilityInvocation": [], "capabilityDelegation": []}
    jcs0 = json.dumps(doc0, sort_keys=True)
    jcs1 = json.dumps(doc1, sort_keys=True)
    await store.add_did_documents([jcs0, jcs1], 0)
    full = f"{jcs0}\n{jcs1}"
    offset = len(jcs0) + 1
    from_offset = await store.get_microledger_from_byte_offset("did:webplus:example.com:x", offset)
    assert from_offset == jcs1
    assert await store.get_microledger_from_byte_offset("did:webplus:example.com:x", 0) == full
    assert await store.get_microledger_from_byte_offset("did:webplus:example.com:x", 9999) == ""
