"""Tests for self-hash verification."""

import json

import pytest
import rfc8785

from did_webplus.selfhash import (
    BLAKE3_PLACEHOLDER,
    SelfHashError,
    compute_self_hash,
    verify_self_hash,
)


def test_placeholder_format() -> None:
    assert BLAKE3_PLACEHOLDER.startswith("u")
    assert len(BLAKE3_PLACEHOLDER) == 47  # multihash format (34 bytes base64url)


def test_verify_rejects_placeholder() -> None:
    doc = {
        "selfHash": BLAKE3_PLACEHOLDER,
        "id": "did:webplus:example.com:" + BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {"key": "dummy"},
        "proofs": [],
    }
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="placeholder"):
        verify_self_hash(jcs)


def test_verify_rejects_missing_self_hash() -> None:
    doc = {"id": "did:webplus:example.com:abc", "validFrom": "2024-01-01T00:00:00.000Z"}
    jcs = json.dumps(doc)
    with pytest.raises(SelfHashError, match="no selfHash"):
        verify_self_hash(jcs)


def test_verify_rejects_tampered_hash() -> None:
    doc = {
        "selfHash": BLAKE3_PLACEHOLDER,
        "id": "did:webplus:example.com:" + BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
    }
    real_hash = compute_self_hash(doc, algorithm="blake3")
    jcs = rfc8785.dumps(doc).decode("utf-8")
    result = verify_self_hash(jcs)
    assert result == real_hash

    # Tamper with a character to produce valid base64url but wrong digest
    tampered_hash = real_hash[:-2] + ("Y" if real_hash[-2] != "Y" else "Z") + real_hash[-1]
    tampered = jcs.replace(real_hash, tampered_hash)
    with pytest.raises(SelfHashError, match="mismatch"):
        verify_self_hash(tampered)


def _root_doc_with_vm() -> dict:
    """Minimal root document with one fully-qualified VM id/kid (placeholders)."""
    did = f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}"
    fq = f"{did}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0"
    return {
        "id": did,
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {"key": "dummy"},
        "proofs": [],
        "verificationMethod": [
            {
                "id": fq,
                "type": "JsonWebKey2020",
                "controller": did,
                "publicKeyJwk": {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    "kid": fq,
                },
            }
        ],
        "authentication": ["#0"],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }


def test_verify_rejects_vm_id_query_param_order() -> None:
    doc = _root_doc_with_vm()
    compute_self_hash(doc, algorithm="blake3")
    vm = doc["verificationMethod"][0]
    # Swap query param order after hashing (self-hash still consistent numerically).
    sh = doc["selfHash"]
    vm["id"] = f"{doc['id']}?versionId=0&selfHash={sh}#0"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="selfHash followed by versionId"):
        verify_self_hash(jcs)


def test_verify_rejects_vm_id_missing_fragment() -> None:
    doc = _root_doc_with_vm()
    compute_self_hash(doc, algorithm="blake3")
    sh = doc["selfHash"]
    doc["verificationMethod"][0]["id"] = f"{doc['id']}?selfHash={sh}&versionId=0"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="missing fragment"):
        verify_self_hash(jcs)


def test_verify_rejects_vm_id_version_id_mismatch() -> None:
    doc = _root_doc_with_vm()
    compute_self_hash(doc, algorithm="blake3")
    sh = doc["selfHash"]
    doc["verificationMethod"][0]["id"] = f"{doc['id']}?selfHash={sh}&versionId=99#0"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="selfHash followed by versionId"):
        verify_self_hash(jcs)


def test_verify_rejects_kid_not_fully_qualified() -> None:
    doc = _root_doc_with_vm()
    compute_self_hash(doc, algorithm="blake3")
    doc["verificationMethod"][0]["publicKeyJwk"]["kid"] = f"{doc['id']}#0"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="not fully-qualified"):
        verify_self_hash(jcs)


def test_verify_rejects_non_root_vm_id_wrong_query_order() -> None:
    # Non-root path suffix is the root hash (not a self-hash slot).
    root_hash = "uHiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    ph = BLAKE3_PLACEHOLDER
    did = f"did:webplus:example.com:{root_hash}"
    fq = f"{did}?selfHash={ph}&versionId=1#0"
    doc = {
        "id": did,
        "selfHash": ph,
        "prevDIDDocumentSelfHash": root_hash,
        "validFrom": "2024-01-02T00:00:00.000Z",
        "versionId": 1,
        "updateRules": {"hashedKey": "dummy"},
        "proofs": [],
        "verificationMethod": [
            {
                "id": fq,
                "type": "JsonWebKey2020",
                "controller": did,
                "publicKeyJwk": {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    "kid": fq,
                },
            }
        ],
        "authentication": ["#0"],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    compute_self_hash(doc, algorithm="blake3")
    sh = doc["selfHash"]
    doc["verificationMethod"][0]["id"] = f"{doc['id']}?versionId=1&selfHash={sh}#0"
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="selfHash followed by versionId"):
        verify_self_hash(jcs)
