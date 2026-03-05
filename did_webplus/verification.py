"""Update rules and proof verification for did:webplus."""

from __future__ import annotations

import base64
import copy
import json
import logging
from typing import Any

import rfc8785

logger = logging.getLogger(__name__)
from jwcrypto import jwk, jws
from multiformats import multibase

from did_webplus.selfhash import (
    _parse_hash,
    _replace_self_hash_slots_in_place,
    hash_bytes_for_hashed_key,
)


class VerificationError(Exception):
    """Proof or update rules verification failed."""


def _jcs_serialize(obj: Any) -> bytes:
    return rfc8785.dumps(obj)


def _bytes_to_sign(doc: dict[str, Any]) -> bytes:
    """
    Bytes that must be signed for a proof.

    JCS of document with proofs removed (not empty array) and self-hash slots = placeholder.
    Placeholder format must match the document's selfHash algorithm (BLAKE3, SHA3-256, etc.).
    Per Rust did-webplus: proofs is skip_serializing_if empty, so omit the key entirely.
    """
    doc_copy = copy.deepcopy(doc)
    doc_copy.pop("proofs", None)  # Remove proofs key entirely; Rust omits it when empty
    _, _, placeholder = _parse_hash(doc["selfHash"])
    _replace_self_hash_slots_in_place(doc_copy, placeholder)
    return _jcs_serialize(doc_copy)


def jwk_to_multibase_key(key: jwk.JWK) -> str:
    """Export Ed25519 JWK public key as multibase-encoded multicodec (u...)."""
    pub = key.export_public(as_dict=True)
    if pub.get("kty") != "OKP" or pub.get("crv") != "Ed25519":
        raise VerificationError("Only Ed25519 OKP keys supported")
    x = base64.urlsafe_b64decode(pub["x"] + "==")
    multicodec = bytes([0xED, 0x01]) + x
    return multibase.encode(multicodec, "base64url")


def create_proof(doc: dict[str, Any], key: jwk.JWK) -> str:
    """
    Create a detached JWS proof for a DID document update.

    The doc must have selfHash set (placeholder or final). The proof signs over
    the bytes-to-sign (JCS with proofs removed and self-hash slots replaced).
    Returns compact detached JWS (header..signature, no payload).
    """
    import jwcrypto.jwa as jwa_module

    if "Ed25519" not in jwa_module.JWA.algorithms_registry:
        jwa_module.JWA.algorithms_registry["Ed25519"] = (
            jwa_module.JWA.algorithms_registry["EdDSA"]
        )
    payload_bytes = _bytes_to_sign(doc)
    kid = jwk_to_multibase_key(key)
    protected = json.dumps(
        {"alg": "Ed25519", "kid": kid, "crit": ["b64"], "b64": False},
        separators=(",", ":"),
    )
    token = jws.JWS(payload_bytes)
    token.allowed_algs = list(jws.default_allowed_algs) + ["Ed25519"]
    token.add_signature(key, protected=protected)
    token.detach_payload()  # required for b64=false: compact encoding rejects payload with "."
    return token.serialize(compact=True)  # yields header..signature (empty payload)


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


def _decode_multibase_key(key_str: str) -> bytes:
    """
    Decode a multibase-encoded multicodec public key (e.g. kid or updateRules key).

    Supports 'u' (base64url) and 'z' (base58btc) prefixes.
    """
    return multibase.decode(key_str)


def _verify_proof(proof_jws: str, payload_bytes: bytes) -> jwk.JWK | None:
    """
    Verify a JWS proof over the detached payload.

    Returns the public key (as JWK) if verification succeeds, else None.
    kid is multibase-encoded multicodec public key (e.g. u7Q... for Ed25519).
    Registers "Ed25519" as alias for "EdDSA" so we keep the original header
    (changing it would alter the signing input and break verification).
    """
    try:
        # jwcrypto only has "EdDSA" in its registry; some JWS use "Ed25519".
        # Register Ed25519 as alias so we can verify without modifying the header
        # (header modification would change the signing input).
        import jwcrypto.jwa as jwa_module

        if "Ed25519" not in jwa_module.JWA.algorithms_registry:
            jwa_module.JWA.algorithms_registry["Ed25519"] = (
                jwa_module.JWA.algorithms_registry["EdDSA"]
            )
        token = jws.JWS()
        token.allowed_algs = list(jws.default_allowed_algs) + ["Ed25519"]
        token.deserialize(proof_jws)
        kid = token.jose_header.get("kid")
        if not kid:
            return None
        key_bytes = _decode_multibase_key(kid)
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
    logger.debug(
        "verification: verify_proofs did=%s versionId=%s num_proofs=%d prev_doc=%s",
        doc.get("id"),
        doc.get("versionId"),
        len(doc.get("proofs", [])),
        "yes" if prev_doc else "no",
    )
    payload_bytes = _bytes_to_sign(doc)
    valid_keys: list[jwk.JWK] = []
    for i, proof in enumerate(doc.get("proofs", [])):
        key = _verify_proof(proof, payload_bytes)
        if key is not None:
            valid_keys.append(key)
            logger.debug("verification: proof[%d] valid", i)
        else:
            logger.debug("verification: proof[%d] invalid or failed", i)

    valid_pub_keys_b64: list[str] = []
    for k in valid_keys:
        export = k.export_public(as_dict=True)
        if "x" in export:
            valid_pub_keys_b64.append(export["x"])
        else:
            valid_pub_keys_b64.append(export.get("x", ""))

    if prev_doc is not None:
        update_rules = prev_doc.get("updateRules", {})
        if update_rules == {}:
            logger.warning("verification: prev_doc has UpdatesDisallowed")
            raise VerificationError("Previous document has UpdatesDisallowed")
        if not _verify_update_rules(update_rules, valid_keys):
            logger.warning(
                "verification: valid proofs do not satisfy updateRules "
                "did=%s updateRules=%s num_valid_keys=%d",
                doc.get("id"),
                update_rules,
                len(valid_keys),
            )
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
        key_str = rules["key"]
        target_bytes = _decode_multibase_key(key_str)
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
            kid_str = multibase.encode(raw, "base64url")
            enc = hash_bytes_for_hashed_key(kid_str.encode("utf-8"), hashed)
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
    export = key.export_public(as_dict=True)
    if export.get("kty") == "OKP" and export.get("crv") == "Ed25519":
        raw = base64.urlsafe_b64decode(export["x"] + "==")
        return bytes([0xED, 0x01]) + raw
    if export.get("kty") == "EC" and export.get("crv") == "P-256":
        x = base64.urlsafe_b64decode(export["x"] + "==")
        y = base64.urlsafe_b64decode(export["y"] + "==")
        return bytes([0x12, 0x00]) + bytes([4]) + x + y
    raise VerificationError(f"Cannot export key type: {export.get('kty')}")
