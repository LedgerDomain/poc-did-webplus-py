"""Focused tests for resolver conformance fixes (crypto, self-hash, JSONL, proofs)."""

from __future__ import annotations

import base64
import json

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, ed448
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from multiformats import multicodec
from multiformats.varint import decode

from did_webplus.resolver import ResolutionError, _split_jsonl_records, _validate_document
from did_webplus.selfhash import (
    BLAKE3_PLACEHOLDER,
    SelfHashError,
    compute_self_hash,
    verify_is_canonically_serialized,
    verify_self_hash,
)
from did_webplus.verification import (
    VerificationError,
    _multicodec_to_jwk,
    _pub_key_to_multicodec_bytes,
    verify_proofs,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.mark.parametrize(
    "codec_name,key_material,crv,kty",
    [
        ("ed25519-pub", ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw(), "Ed25519", "OKP"),
        ("ed448-pub", ed448.Ed448PrivateKey.generate().public_key().public_bytes_raw(), "Ed448", "OKP"),
    ],
)
def test_multicodec_okp_roundtrip(codec_name: str, key_material: bytes, crv: str, kty: str) -> None:
    wrapped = multicodec.wrap(codec_name, key_material)
    key = _multicodec_to_jwk(wrapped)
    export = key.export_public(as_dict=True)
    assert export["kty"] == kty
    assert export["crv"] == crv
    assert _pub_key_to_multicodec_bytes(key) == wrapped


@pytest.mark.parametrize(
    "codec_name,curve,crv",
    [
        ("p256-pub", ec.SECP256R1(), "P-256"),
        ("p384-pub", ec.SECP384R1(), "P-384"),
        ("p521-pub", ec.SECP521R1(), "P-521"),
        ("secp256k1-pub", ec.SECP256K1(), "secp256k1"),
    ],
)
def test_multicodec_ec_compressed_roundtrip(codec_name: str, curve: ec.EllipticCurve, crv: str) -> None:
    pub = ec.generate_private_key(curve).public_key()
    compressed = pub.public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
    wrapped = multicodec.wrap(codec_name, compressed)
    # Confirm varint (not fixed 2-byte BE) for multi-byte codes
    from io import BytesIO

    buf = BytesIO(wrapped)
    code = decode(buf)
    assert code == multicodec.get(codec_name).code
    assert buf.read() == compressed

    key = _multicodec_to_jwk(wrapped)
    export = key.export_public(as_dict=True)
    assert export["kty"] == "EC"
    assert export["crv"] == crv
    assert _pub_key_to_multicodec_bytes(key) == wrapped


def test_base58btc_self_hash_roundtrip() -> None:
    doc = {
        "id": "did:webplus:example.com:PLACEHOLDER",
        "selfHash": "PLACEHOLDER",
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
    from did_webplus.selfhash import BLAKE3_PLACEHOLDER

    doc["id"] = f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}"
    doc["selfHash"] = BLAKE3_PLACEHOLDER
    result = compute_self_hash(doc, algorithm="blake3", multibase_name="base58btc")
    assert result.startswith("z")
    assert doc["selfHash"] == result
    assert doc["id"].endswith(result)
    jcs = rfc8785.dumps(doc).decode("utf-8")
    assert verify_self_hash(jcs) == result


def test_wire_jcs_rejects_extra_whitespace() -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "uHiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
    }
    wire = json.dumps(doc) + " "
    with pytest.raises(SelfHashError, match="not in JCS form"):
        verify_is_canonically_serialized(doc, wire)


def test_split_jsonl_rejects_blank_lines() -> None:
    with pytest.raises(ResolutionError, match="blank line"):
        _split_jsonl_records('{"a":1}\n\n{"b":2}\n')


def test_split_jsonl_rejects_crlf() -> None:
    with pytest.raises(ResolutionError, match="CR"):
        _split_jsonl_records('{"a":1}\r\n{"b":2}\n')


def test_split_jsonl_allows_trailing_newline() -> None:
    assert _split_jsonl_records('{"a":1}\n{"b":2}\n') == ['{"a":1}', '{"b":2}']


def test_verify_proofs_hard_fails_invalid_proof() -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "uEiCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": ["e30..AAAA"],  # malformed / invalid
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    with pytest.raises(VerificationError):
        verify_proofs(doc, None)


def test_inconsistent_self_hash_slots_rejected() -> None:
    doc = {
        "id": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}",
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [
            {
                "id": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0",
                "type": "JsonWebKey2020",
                "controller": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}",
                "publicKeyJwk": {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": _b64url(b"\x01" * 32),
                    "kid": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0",
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
    # Tamper VM selfHash query after hashing (slots no longer consistent)
    bad = "uHiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    vm = doc["verificationMethod"][0]
    vm["id"] = vm["id"].replace(doc["selfHash"], bad, 1)
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(SelfHashError, match="self-hash-slot-mismatch"):
        verify_self_hash(jcs)


def test_validate_document_rejects_string_version_id() -> None:
    doc = {
        "id": "did:webplus:example.com:abc",
        "selfHash": "uEiCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": "0",
        "updateRules": {},
        "proofs": [],
    }
    jcs = rfc8785.dumps(doc).decode("utf-8")
    with pytest.raises(ResolutionError, match="versionId must be a JSON integer"):
        _validate_document(jcs, doc, None)
