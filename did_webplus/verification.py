"""Update rules and proof verification for did:webplus."""

from __future__ import annotations

import base64
import copy
import json
from typing import Any

import blake3
import rfc8785
from jwcrypto import jwk, jws

from did_webplus.selfhash import BLAKE3_PLACEHOLDER, _replace_self_hash_slots_in_place


class VerificationError(Exception):
    """Proof or update rules verification failed."""


def _jcs_serialize(obj: Any) -> bytes:
    return rfc8785.dumps(obj)


def _bytes_to_sign(doc: dict[str, Any]) -> bytes:
    """
    Bytes that must be signed for a proof.

    JCS of document with proofs cleared and self-hash slots = placeholder.
    """
    doc_copy = copy.deepcopy(doc)
    doc_copy["proofs"] = []
    _replace_self_hash_slots_in_place(doc_copy, BLAKE3_PLACEHOLDER)
    return _jcs_serialize(doc_copy)


def _multicodec_to_jwk(key_bytes: bytes) -> jwk.JWK:
    """
    Convert multicodec-encoded public key to JWK.

    Supports Ed25519 (0xed01) and P-256 (0x1200).
    """
    if len(key_bytes) < 2:
        raise VerificationError(f"Key too short: {len(key_bytes)} bytes")

    prefix = key_bytes[0] << 8 | key_bytes[1]
    if prefix == 0xED01:
        if len(key_bytes) != 34:
            raise VerificationError(
                f"Ed25519 key must be 34 bytes (2 prefix + 32 key), got {len(key_bytes)}"
            )
        raw_key = key_bytes[2:]
        x_b64 = base64.urlsafe_b64encode(raw_key).rstrip(b"=").decode("ascii")
        return jwk.JWK.from_json(
            json.dumps({"kty": "OKP", "crv": "Ed25519", "x": x_b64})
        )
    if prefix == 0x1200:
        if len(key_bytes) != 67:
            raise VerificationError(
                f"P-256 key must be 67 bytes (2 prefix + 65 uncompressed), got {len(key_bytes)}"
            )
        raw_key = key_bytes[2:]
        if raw_key[0] != 0x04:
            raise VerificationError("P-256 key must be uncompressed (0x04)")
        x = raw_key[1:33]
        y = raw_key[33:65]
        x_b64 = base64.urlsafe_b64encode(x).rstrip(b"=").decode("ascii")
        y_b64 = base64.urlsafe_b64encode(y).rstrip(b"=").decode("ascii")
        return jwk.JWK.from_json(
            json.dumps({"kty": "EC", "crv": "P-256", "x": x_b64, "y": y_b64})
        )
    raise VerificationError(f"Unsupported multicodec prefix: 0x{prefix:04x}")


def _verify_proof(proof_jws: str, payload_bytes: bytes) -> jwk.JWK | None:
    """
    Verify a JWS proof over the detached payload.

    Returns the public key (as JWK) if verification succeeds, else None.
    """
    try:
        token = jws.JWS()
        token.deserialize(proof_jws)
        kid = token.jose_header.get("kid")
        if not kid:
            return None
        key_bytes = base64.urlsafe_b64decode(kid + "==")
        key = _multicodec_to_jwk(key_bytes)
        token.verify(key, detached_payload=payload_bytes)
        return key
    except Exception:
        return None


def verify_proofs(
    doc: dict[str, Any],
    prev_doc: dict[str, Any] | None,
) -> list[str]:
    """
    Verify all proofs and return list of valid proof public keys (base64url).

    For non-root, the valid proof keys must satisfy prev_doc's updateRules.
    """
    payload_bytes = _bytes_to_sign(doc)
    valid_keys: list[jwk.JWK] = []
    for proof in doc.get("proofs", []):
        key = _verify_proof(proof, payload_bytes)
        if key is not None:
            valid_keys.append(key)

    valid_pub_keys_b64: list[str] = []
    for k in valid_keys:
        export = k.export_public()
        if "x" in export:
            valid_pub_keys_b64.append(export["x"])
        else:
            valid_pub_keys_b64.append(export.get("x", ""))

    if prev_doc is not None:
        update_rules = prev_doc.get("updateRules", {})
        if update_rules == {}:
            raise VerificationError("Previous document has UpdatesDisallowed")
        if not _verify_update_rules(update_rules, valid_keys):
            raise VerificationError(
                "Valid proofs do not satisfy previous document's updateRules"
            )

    return valid_pub_keys_b64


def _verify_update_rules(rules: dict[str, Any], valid_keys: list[jwk.JWK]) -> bool:
    """Check if any valid key satisfies the update rules."""
    try:
        _verify_update_rules_inner(rules, valid_keys)
        return True
    except VerificationError:
        return False


def _verify_update_rules_inner(
    rules: dict[str, Any], valid_keys: list[jwk.JWK]
) -> None:
    """Recursively verify update rules. Raises if not satisfied."""
    if "key" in rules:
        key_b64 = rules["key"]
        key_bytes = base64.urlsafe_b64decode(key_b64 + "==")
        target_bytes = key_bytes
        for k in valid_keys:
            try:
                our_bytes = _pub_key_to_multicodec_bytes(k)
                if our_bytes == target_bytes:
                    return
            except VerificationError:
                pass
        raise VerificationError("Key rule not satisfied: no matching proof")

    if "hashedKey" in rules:
        hashed = rules["hashedKey"]
        for k in valid_keys:
            raw = _pub_key_to_multicodec_bytes(k)
            h = blake3.blake3(raw).digest()
            enc = "E" + base64.urlsafe_b64encode(h).rstrip(b"=").decode("ascii")
            if enc == hashed:
                return
        raise VerificationError("HashedKey rule not satisfied")

    if "any" in rules:
        for sub in rules["any"]:
            try:
                _verify_update_rules_inner(sub, valid_keys)
                return
            except VerificationError:
                continue
        raise VerificationError("Any rule: no subordinate rule satisfied")

    if "all" in rules:
        for sub in rules["all"]:
            _verify_update_rules_inner(sub, valid_keys)
        return

    if "atLeast" in rules and "of" in rules:
        at_least = rules["atLeast"]
        weight_sum = 0
        for w in rules["of"]:
            weight = w.get("weight", 1)
            sub = {k: v for k, v in w.items() if k != "weight"}
            try:
                _verify_update_rules_inner(sub, valid_keys)
                weight_sum += weight
            except VerificationError:
                pass
        if weight_sum >= at_least:
            return
        raise VerificationError(
            f"atLeast {at_least} not met (weight sum {weight_sum})"
        )

    if rules == {}:
        raise VerificationError("UpdatesDisallowed")

    raise VerificationError(f"Unknown update rule structure: {list(rules.keys())}")


def _pub_key_to_multicodec_bytes(key: jwk.JWK) -> bytes:
    """Export JWK to multicodec bytes for hashing."""
    export = key.export_public()
    if export.get("kty") == "OKP" and export.get("crv") == "Ed25519":
        raw = base64.urlsafe_b64decode(export["x"] + "==")
        return bytes([0xED, 0x01]) + raw
    if export.get("kty") == "EC" and export.get("crv") == "P-256":
        x = base64.urlsafe_b64decode(export["x"] + "==")
        y = base64.urlsafe_b64decode(export["y"] + "==")
        return bytes([0x12, 0x00]) + bytes([4]) + x + y
    raise VerificationError(f"Cannot export key type: {export.get('kty')}")
