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
