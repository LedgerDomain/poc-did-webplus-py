"""Tests for DID document model and validation."""

import pytest

from did_webplus.document import DIDDocument, parse_did_document


def test_parse_root_document() -> None:
    doc_json = """{
        "id": "did:webplus:example.com:abc123",
        "selfHash": "Exyz",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {"key": "dummy"},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": []
    }"""
    doc = parse_did_document(doc_json)
    assert doc.id == "did:webplus:example.com:abc123"
    assert doc.version_id == 0
    assert doc.is_root_document()
    assert not doc.is_deactivated()


def test_parse_non_root_document() -> None:
    doc_json = """{
        "id": "did:webplus:example.com:abc123",
        "selfHash": "Exyz2",
        "prevDIDDocumentSelfHash": "Exyz",
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 1,
        "updateRules": {"key": "dummy"},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": []
    }"""
    doc = parse_did_document(doc_json)
    assert doc.version_id == 1
    assert not doc.is_root_document()
    assert doc.prevDIDDocumentSelfHash == "Exyz"


def test_verify_chain_root_ok() -> None:
    doc_json = """{
        "id": "did:webplus:example.com:abc",
        "selfHash": "E1",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": []
    }"""
    doc = parse_did_document(doc_json)
    doc.verify_chain_constraints(None)


def test_verify_chain_non_root_ok() -> None:
    root_json = """{
        "id": "did:webplus:example.com:abc",
        "selfHash": "Eroot",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": []
    }"""
    non_root_json = """{
        "id": "did:webplus:example.com:abc",
        "selfHash": "E2",
        "prevDIDDocumentSelfHash": "Eroot",
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 1,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": []
    }"""
    root = parse_did_document(root_json)
    non_root = parse_did_document(non_root_json)
    non_root.verify_chain_constraints(root)


def test_verify_chain_rejects_wrong_prev_hash() -> None:
    root = parse_did_document('''{
        "id": "did:webplus:example.com:abc",
        "selfHash": "Eroot",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [], "assertionMethod": [], "keyAgreement": [],
        "capabilityInvocation": [], "capabilityDelegation": []
    }''')
    non_root = parse_did_document('''{
        "id": "did:webplus:example.com:abc",
        "selfHash": "E2",
        "prevDIDDocumentSelfHash": "Ewrong",
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 1,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [], "assertionMethod": [], "keyAgreement": [],
        "capabilityInvocation": [], "capabilityDelegation": []
    }''')
    with pytest.raises(ValueError, match="prevDIDDocumentSelfHash"):
        non_root.verify_chain_constraints(root)


def test_verify_chain_rejects_wrong_version_id() -> None:
    root = parse_did_document('''{
        "id": "did:webplus:example.com:abc",
        "selfHash": "Eroot",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [], "assertionMethod": [], "keyAgreement": [],
        "capabilityInvocation": [], "capabilityDelegation": []
    }''')
    non_root = parse_did_document('''{
        "id": "did:webplus:example.com:abc",
        "selfHash": "E2",
        "prevDIDDocumentSelfHash": "Eroot",
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 2,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [], "assertionMethod": [], "keyAgreement": [],
        "capabilityInvocation": [], "capabilityDelegation": []
    }''')
    with pytest.raises(ValueError, match="versionId"):
        non_root.verify_chain_constraints(root)


def test_is_deactivated() -> None:
    doc = parse_did_document('''{
        "id": "did:webplus:example.com:abc",
        "selfHash": "E1",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [], "assertionMethod": [], "keyAgreement": [],
        "capabilityInvocation": [], "capabilityDelegation": []
    }''')
    assert doc.is_deactivated()
