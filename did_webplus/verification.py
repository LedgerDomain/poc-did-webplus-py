"""Update rules and proof verification for did:webplus."""

from __future__ import annotations

import base64
import copy
import json
import logging
from typing import Any

import rfc8785
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from jwcrypto import jwk, jws
from multiformats import multibase, multicodec

from did_webplus.selfhash import (
    _parse_hash,
    _replace_self_hash_slots_in_place,
    hash_bytes_for_hashed_key,
)

logger = logging.getLogger(__name__)

# JWS algs used by did:webplus proofs (beyond jwcrypto defaults for Ed* aliases).
_PROOF_ALGS = list(jws.default_allowed_algs) + ["Ed25519", "Ed448"]

_OKP_CODE_TO_CRV = {
    "ed25519-pub": ("Ed25519", 32),
    "ed448-pub": ("Ed448", 57),
}

_EC_CODE_TO_CURVE = {
    "p256-pub": (ec.SECP256R1(), "P-256"),
    "p384-pub": (ec.SECP384R1(), "P-384"),
    "p521-pub": (ec.SECP521R1(), "P-521"),
    "secp256k1-pub": (ec.SECP256K1(), "secp256k1"),
}

_CRV_TO_CODE = {
    "Ed25519": "ed25519-pub",
    "Ed448": "ed448-pub",
    "P-256": "p256-pub",
    "P-384": "p384-pub",
    "P-521": "p521-pub",
    "secp256k1": "secp256k1-pub",
}


class VerificationError(Exception):
    """Proof or update rules verification failed."""


def _ensure_eddsa_alg_aliases() -> None:
    """Register Ed25519/Ed448 as EdDSA aliases without rewriting JWS headers."""
    import jwcrypto.jwa as jwa_module

    eddsa = jwa_module.JWA.algorithms_registry["EdDSA"]
    for name in ("Ed25519", "Ed448"):
        if name not in jwa_module.JWA.algorithms_registry:
            jwa_module.JWA.algorithms_registry[name] = eddsa


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


def _b64url_uint(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "==")


def jwk_to_multibase_key(key: jwk.JWK) -> str:
    """Export a public JWK as multibase-encoded multicodec (u...)."""
    return multibase.encode(_pub_key_to_multicodec_bytes(key), "base64url")


def create_proof(doc: dict[str, Any], key: jwk.JWK) -> str:
    """
    Create a detached JWS proof for a DID document update.

    The doc must have selfHash set (placeholder or final). The proof signs over
    the bytes-to-sign (JCS with proofs removed and self-hash slots replaced).
    Returns compact detached JWS (header..signature, no payload).
    """
    _ensure_eddsa_alg_aliases()
    payload_bytes = _bytes_to_sign(doc)
    kid = jwk_to_multibase_key(key)
    pub = key.export_public(as_dict=True)
    if pub.get("kty") == "OKP" and pub.get("crv") == "Ed25519":
        alg = "Ed25519"
    elif pub.get("kty") == "OKP" and pub.get("crv") == "Ed448":
        alg = "Ed448"
    elif pub.get("kty") == "EC" and pub.get("crv") == "P-256":
        alg = "ES256"
    elif pub.get("kty") == "EC" and pub.get("crv") == "P-384":
        alg = "ES384"
    elif pub.get("kty") == "EC" and pub.get("crv") == "P-521":
        alg = "ES512"
    elif pub.get("kty") == "EC" and pub.get("crv") == "secp256k1":
        alg = "ES256K"
    else:
        raise VerificationError(f"Unsupported key for proof: {pub.get('kty')}/{pub.get('crv')}")
    protected = json.dumps(
        {"alg": alg, "kid": kid, "crit": ["b64"], "b64": False},
        separators=(",", ":"),
    )
    token = jws.JWS(payload_bytes)
    token.allowed_algs = list(_PROOF_ALGS)
    token.add_signature(key, protected=protected)
    token.detach_payload()  # required for b64=false: compact encoding rejects payload with "."
    return token.serialize(compact=True)  # yields header..signature (empty payload)


def _multicodec_to_jwk(key_bytes: bytes) -> jwk.JWK:
    """
    Convert multicodec-encoded public key to JWK.

    Multicodec code is an unsigned varint. EC keys use compressed SEC1 points.
    """
    try:
        codec, key_material = multicodec.unwrap(key_bytes)
    except Exception as e:
        raise VerificationError(f"Invalid multicodec key: {e}") from e

    if codec.name in _OKP_CODE_TO_CRV:
        crv, expected_len = _OKP_CODE_TO_CRV[codec.name]
        if len(key_material) != expected_len:
            raise VerificationError(
                f"{crv} key must be {expected_len} bytes, got {len(key_material)}"
            )
        return jwk.JWK.from_json(
            json.dumps(
                {
                    "kty": "OKP",
                    "crv": crv,
                    "x": _b64url_uint(key_material),
                }
            )
        )

    if codec.name in _EC_CODE_TO_CURVE:
        curve, crv_name = _EC_CODE_TO_CURVE[codec.name]
        try:
            pub = ec.EllipticCurvePublicKey.from_encoded_point(curve, key_material)
        except Exception as e:
            raise VerificationError(f"Invalid {crv_name} public key: {e}") from e
        nums = pub.public_numbers()
        byte_len = (nums.curve.key_size + 7) // 8
        x = nums.x.to_bytes(byte_len, "big")
        y = nums.y.to_bytes(byte_len, "big")
        return jwk.JWK.from_json(
            json.dumps(
                {
                    "kty": "EC",
                    "crv": crv_name,
                    "x": _b64url_uint(x),
                    "y": _b64url_uint(y),
                }
            )
        )

    raise VerificationError(f"Unsupported multicodec: {codec.name} ({hex(codec.code)})")


def _decode_multibase_key(key_str: str) -> bytes:
    """
    Decode a multibase-encoded multicodec public key (e.g. kid or updateRules key).

    Supports 'u' (base64url) and 'z' (base58btc) prefixes.
    """
    return multibase.decode(key_str)


def _verify_proof(proof_jws: str, payload_bytes: bytes) -> jwk.JWK:
    """
    Verify a JWS proof over the detached payload.

    Returns the public key (as JWK) if verification succeeds.
    Raises VerificationError on any failure.
    """
    try:
        _ensure_eddsa_alg_aliases()
        token = jws.JWS()
        token.allowed_algs = list(_PROOF_ALGS)
        token.deserialize(proof_jws)
        kid = token.jose_header.get("kid")
        if not kid:
            raise VerificationError("Proof JWS header missing kid")
        key_bytes = _decode_multibase_key(kid)
        key = _multicodec_to_jwk(key_bytes)
        token.verify(key, detached_payload=payload_bytes)
        return key
    except VerificationError:
        raise
    except Exception as e:
        raise VerificationError(f"Proof verification failed: {e}") from e


def verify_proofs(
    doc: dict[str, Any],
    prev_doc: dict[str, Any] | None,
) -> list[str]:
    """
    Verify all proofs and return list of valid proof public keys (base64url).

    Every entry in proofs[] must cryptographically verify. For non-root, the
    valid proof keys must also satisfy prev_doc's updateRules.
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
        valid_keys.append(key)
        logger.debug("verification: proof[%d] valid", i)

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
    """Export JWK to multicodec bytes (varint code + key material; EC compressed)."""
    export = key.export_public(as_dict=True)
    kty = export.get("kty")
    crv = export.get("crv")
    code_name = _CRV_TO_CODE.get(crv) if crv else None
    if kty == "OKP" and code_name in _OKP_CODE_TO_CRV:
        raw = _b64url_decode(export["x"])
        expected = _OKP_CODE_TO_CRV[code_name][1]
        if len(raw) != expected:
            raise VerificationError(
                f"{crv} key must be {expected} bytes, got {len(raw)}"
            )
        return multicodec.wrap(code_name, raw)
    if kty == "EC" and code_name in _EC_CODE_TO_CURVE:
        curve, _ = _EC_CODE_TO_CURVE[code_name]
        x = int.from_bytes(_b64url_decode(export["x"]), "big")
        y = int.from_bytes(_b64url_decode(export["y"]), "big")
        pub = ec.EllipticCurvePublicNumbers(x, y, curve).public_key()
        compressed = pub.public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
        return multicodec.wrap(code_name, compressed)
    raise VerificationError(f"Cannot export key type: {kty}/{crv}")
