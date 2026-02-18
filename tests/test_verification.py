"""Tests for update rules and proof verification."""

import json

import pytest

from did_webplus.verification import (
    VerificationError,
    verify_proofs,
    _bytes_to_sign,
)


def test_bytes_to_sign_clears_proofs() -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Eplaceholder",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {"key": "dummy"},
        "proofs": ["some-proof"],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    result = _bytes_to_sign(doc)
    parsed = json.loads(result.decode("utf-8"))
    assert parsed.get("proofs") == []


def test_verify_proofs_root_empty_proofs() -> None:
    doc = {
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
        "capabilityDelegation": [],
    }
    verify_proofs(doc, None)


def test_verify_proofs_non_root_updates_disallowed() -> None:
    prev = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "Eprev",
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
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "E2",
        "prevDIDDocumentSelfHash": "Eprev",
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
    with pytest.raises(VerificationError, match="UpdatesDisallowed"):
        verify_proofs(doc, prev)
