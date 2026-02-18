"""Tests for self-hash verification."""

import json

import pytest
import rfc8785

from did_webplus.selfhash import (
    BLAKE3_PLACEHOLDER,
    SelfHashError,
    verify_self_hash,
)


def test_placeholder_format() -> None:
    assert BLAKE3_PLACEHOLDER.startswith("E")
    assert len(BLAKE3_PLACEHOLDER) == 44


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
    import blake3
    import base64

    doc = {
        "selfHash": BLAKE3_PLACEHOLDER,
        "id": "did:webplus:example.com:" + BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
    }
    doc["selfHash"] = BLAKE3_PLACEHOLDER
    msg = rfc8785.dumps(doc)
    digest = blake3.blake3(msg).digest()
    real_hash = "E" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    doc["selfHash"] = real_hash
    doc["id"] = "did:webplus:example.com:" + real_hash
    jcs = rfc8785.dumps(doc).decode("utf-8")
    result = verify_self_hash(jcs)
    assert result == real_hash

    tampered = jcs.replace(real_hash, real_hash[:-1] + "X")
    with pytest.raises(SelfHashError, match="mismatch"):
        verify_self_hash(tampered)
