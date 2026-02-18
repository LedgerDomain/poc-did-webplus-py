"""Tests for update rules and proof verification."""

import json

import pytest

from did_webplus.selfhash import BLAKE3_PLACEHOLDER
from did_webplus.verification import (
    VerificationError,
    verify_proofs,
    _bytes_to_sign,
)


def test_bytes_to_sign_clears_proofs() -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": BLAKE3_PLACEHOLDER,
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
    assert "proofs" not in parsed


def test_verify_proofs_root_empty_proofs() -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
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
    verify_proofs(doc, None)


def test_verify_proofs_non_root_updates_disallowed() -> None:
    prev = {
        "id": "did:webplus:example.com:abc",
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
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": BLAKE3_PLACEHOLDER,
        "prevDIDDocumentSelfHash": BLAKE3_PLACEHOLDER,
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


def test_bytes_to_sign_and_proof_verification_test_vector() -> None:
    """
    Diagnostic test: load test-vector non-root document, compute _bytes_to_sign,
    and verify the JWS proof. Locks in correct payload computation.
    """
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent / "test-vectors" / "valid"
    doc = json.loads((base / "non-root-document.json").read_text())
    prev = json.loads((base / "root-document.json").read_text())

    verify_proofs(doc, prev)
