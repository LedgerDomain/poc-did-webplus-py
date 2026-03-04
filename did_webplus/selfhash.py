"""Self-hash verification for did:webplus DID documents."""

from __future__ import annotations

import copy
import json
from typing import Any

import rfc8785
from multiformats import multibase, multihash

# Placeholder for BLAKE3 self-hash slots (multihash format, same as other algorithms)
BLAKE3_PLACEHOLDER = multibase.encode(
    multihash.get("blake3").wrap(b"\x00" * 32), "base64url"
)


class SelfHashError(Exception):
    """Self-hash verification failed."""


def _jcs_serialize(obj: Any) -> bytes:
    """Canonical JCS serialization."""
    return rfc8785.dumps(obj)


def _parse_hash(hash_str: str) -> tuple[str, bytes, str]:
    """
    Parse hash string. Returns (codec_name, digest, placeholder).
    All hashes use multihash format (code + length + digest).
    """
    if not hash_str or hash_str[0] != "u":
        raise SelfHashError("Hash must start with 'u' (base64url)")
    try:
        raw = multibase.decode(hash_str)
    except Exception as e:
        raise SelfHashError(f"Invalid multibase in hash: {e}") from e

    # Multihash format
    try:
        mh = multihash.from_digest(raw)
    except KeyError as e:
        raise SelfHashError(f"Unsupported multihash code in hash: {e}") from e
    if not multihash.is_implemented(name=mh.name):
        raise SelfHashError(f"Multihash {mh.name!r} not implemented")
    digest = multihash.unwrap(raw)
    placeholder = multibase.encode(mh.wrap(b"\x00" * len(digest)), "base64url")
    return mh.name, digest, placeholder


def _encode_hash(codec_name: str, digest: bytes) -> str:
    """Encode digest as multihash (u + base64url)."""
    mh = multihash.get(codec_name)
    wrapped = mh.wrap(digest)
    return multibase.encode(wrapped, "base64url")


def _get_hash_prefix(hash_str: str) -> str:
    """Get multibase prefix: 'u' for base64url, 'z' for base58btc."""
    if not hash_str:
        raise SelfHashError("Empty hash string")
    return hash_str[0]


def _is_placeholder(hash_str: str) -> bool:
    """Check if the value is any known placeholder."""
    if hash_str == BLAKE3_PLACEHOLDER:
        return True
    try:
        _, _, placeholder = _parse_hash(hash_str)
        return hash_str == placeholder
    except SelfHashError:
        return False


def _replace_self_hash_slots_in_place(doc: dict[str, Any], placeholder: str) -> None:
    """
    Replace all self-hash slots in the document with the placeholder.

    For root: id (last path component), selfHash, verificationMethod[].id (DID part and selfHash param)
    For non-root: selfHash only
    """
    claimed = doc.get("selfHash")
    if not claimed:
        raise SelfHashError("Document has no selfHash field")

    is_root = "prevDIDDocumentSelfHash" not in doc or doc["prevDIDDocumentSelfHash"] is None

    def replace_did_suffix(did_str: str) -> str:
        """Replace the last path component (root self hash) in a DID."""
        if did_str.count(":") < 3:
            return did_str
        prefix = "did:webplus:"
        if not did_str.startswith(prefix):
            return did_str
        rest = did_str[len(prefix) :]
        parts = rest.split(":")
        if not parts:
            return did_str
        parts[-1] = placeholder
        return prefix + ":".join(parts)

    doc["selfHash"] = placeholder

    def replace_did_url(url: str) -> str:
        """Replace DID suffix and selfHash param in a DID or DID URL."""
        if "?" in url:
            did_part, query = url.split("?", 1)
            did_part = replace_did_suffix(did_part)
            params = []
            for param in query.split("&"):
                if "=" in param:
                    k, v = param.split("=", 1)
                    if k == "selfHash":
                        v = placeholder
                    params.append(f"{k}={v}")
            return did_part + "?" + "&".join(params)
        return replace_did_suffix(url)

    if is_root:
        if "id" in doc and doc["id"]:
            doc["id"] = replace_did_url(doc["id"])

        for vm in doc.get("verificationMethod", []):
            if "id" in vm and vm["id"]:
                vm["id"] = replace_did_url(vm["id"])
            if "controller" in vm and vm["controller"]:
                vm["controller"] = replace_did_suffix(vm["controller"])
            jwk = vm.get("publicKeyJwk")
            if isinstance(jwk, dict) and "kid" in jwk and jwk["kid"]:
                jwk["kid"] = replace_did_url(jwk["kid"])
    else:
        # Non-root: replace only selfHash in query params (id path has root hash, not doc's selfHash)
        def replace_query_self_hash(url: str) -> str:
            if "?" not in url:
                return url
            did_part, query = url.split("?", 1)
            params = []
            for param in query.split("&"):
                if "=" in param:
                    k, v = param.split("=", 1)
                    if k == "selfHash":
                        v = placeholder
                    params.append(f"{k}={v}")
            return did_part + "?" + "&".join(params)

        for vm in doc.get("verificationMethod", []):
            if "id" in vm and vm["id"]:
                vm["id"] = replace_query_self_hash(vm["id"])
            jwk = vm.get("publicKeyJwk")
            if isinstance(jwk, dict) and "kid" in jwk and jwk["kid"]:
                jwk["kid"] = replace_query_self_hash(jwk["kid"])


def verify_self_hash(jcs_str: str) -> str:
    """
    Verify the self-hash of a DID document and return the claimed digest.

    Supports BLAKE3, SHA-224, SHA-256, SHA-384, SHA-512, SHA3-224, SHA3-256,
    SHA3-384, SHA3-512 via multicodec detection.

    Returns:
        The verified self-hash string.

    Raises:
        SelfHashError: If verification fails.
    """
    doc = json.loads(jcs_str)
    claimed = doc.get("selfHash")
    if not claimed:
        raise SelfHashError("Document has no selfHash field")

    prefix = _get_hash_prefix(claimed)
    if prefix not in ("u", "z"):
        raise SelfHashError(
            f"Unsupported multibase prefix: {prefix!r} "
            "(expected 'u' for base64url or 'z' for base58btc)"
        )

    if prefix == "z":
        raise SelfHashError("base58btc ('z') self-hash verification not implemented")

    if _is_placeholder(claimed):
        raise SelfHashError("Document has placeholder selfHash, not a real hash")

    codec_name, _, placeholder = _parse_hash(claimed)
    doc_copy = copy.deepcopy(doc)
    _replace_self_hash_slots_in_place(doc_copy, placeholder)
    msg = _jcs_serialize(doc_copy)
    size = 32 if codec_name == "blake3" else None  # BLAKE3 requires explicit size
    digest_bytes = multihash.digest(msg, codec_name, size=size)
    raw_digest = multihash.unwrap(digest_bytes)
    computed = _encode_hash(codec_name, raw_digest)

    if computed != claimed:
        raise SelfHashError(
            f"Self-hash mismatch: computed {computed!r}, claimed {claimed!r}"
        )
    return claimed


def compute_self_hash(
    doc: dict[str, Any],
    *,
    algorithm: str = "blake3",
) -> str:
    """
    Compute and return the self-hash for a document (with placeholder in slots).

    Mutates doc in place to fill in the hash. Use for creating test fixtures.
    All algorithms use multihash format (code + length + digest).
    """
    supported = {
        "blake3",
        "sha2-224",
        "sha2-256",
        "sha2-384",
        "sha2-512",
        "sha3-224",
        "sha3-256",
        "sha3-384",
        "sha3-512",
    }
    if algorithm not in supported:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    mh = multihash.get(algorithm)
    placeholder = multibase.encode(
        mh.wrap(b"\x00" * (mh.max_digest_size or 32)), "base64url"
    )
    _replace_self_hash_slots_in_place(doc, placeholder)
    msg = _jcs_serialize(doc)
    size = 32 if algorithm == "blake3" else None  # BLAKE3 requires explicit size
    digest_bytes = multihash.digest(msg, algorithm, size=size)
    raw_digest = multihash.unwrap(digest_bytes)
    result = _encode_hash(algorithm, raw_digest)
    _replace_self_hash_slots_in_place(doc, result)
    return result


def hash_bytes_for_hashed_key(data: bytes, hash_str: str) -> str:
    """
    Hash bytes using the same algorithm as indicated by hash_str (e.g. from hashedKey).
    Returns the encoded hash (u + base64url).
    """
    codec_name, _, _ = _parse_hash(hash_str)
    size = 32 if codec_name == "blake3" else None  # BLAKE3 requires explicit size
    digest_bytes = multihash.digest(data, codec_name, size=size)
    raw_digest = multihash.unwrap(digest_bytes)
    return _encode_hash(codec_name, raw_digest)


def verify_is_canonically_serialized(doc: dict[str, Any], jcs_str: str) -> None:
    """
    Verify that jcs_str is the JCS-serialized form of doc.

    Raises:
        SelfHashError: If the string does not match.
    """
    canonical = _jcs_serialize(doc).decode("utf-8")
    if canonical != jcs_str:
        raise SelfHashError(
            f"Document is not in JCS form: expected {canonical!r}, got {jcs_str!r}"
        )
