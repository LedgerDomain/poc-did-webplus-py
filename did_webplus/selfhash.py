"""Self-hash verification for did:webplus DID documents."""

from __future__ import annotations

import base64
import copy
import json
from typing import Any

import blake3
import rfc8785

# BLAKE3-256 placeholder: "E" + base64url(32 zero bytes) per selfhash crate
BLAKE3_PLACEHOLDER = "E" + base64.urlsafe_b64encode(b"\x00" * 32).rstrip(b"=").decode("ascii")


class SelfHashError(Exception):
    """Self-hash verification failed."""


def _jcs_serialize(obj: Any) -> bytes:
    """Canonical JCS serialization."""
    return rfc8785.dumps(obj)


def _compute_blake3_base64url(data: bytes) -> str:
    """BLAKE3-256 hash, encoded as base64url (no padding)."""
    digest = blake3.blake3(data).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _get_hash_prefix(hash_str: str) -> str:
    """Get multibase/hash function prefix (e.g. 'E' for BLAKE3)."""
    if not hash_str:
        raise SelfHashError("Empty hash string")
    return hash_str[0]


def _is_placeholder(hash_str: str) -> bool:
    """Check if the value is the BLAKE3 placeholder."""
    return hash_str == BLAKE3_PLACEHOLDER


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

    def replace_in_id(id_val: str) -> str:
        """Replace self-hash in DID or DID URL (id field)."""
        if "?" in id_val:
            did_part, query = id_val.split("?", 1)
            params = []
            for param in query.split("&"):
                if "=" in param:
                    k, v = param.split("=", 1)
                    if k == "selfHash":
                        v = placeholder
                    params.append(f"{k}={v}")
            return did_part + "?" + "&".join(params)
        return id_val

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

    if is_root:
        if "id" in doc and doc["id"]:
            doc["id"] = replace_did_suffix(doc["id"])

        for vm in doc.get("verificationMethod", []):
            if "id" in vm and vm["id"]:
                vm_id = vm["id"]
                if "?" in vm_id:
                    did_part, query = vm_id.split("?", 1)
                    did_part = replace_did_suffix(did_part)
                    params = []
                    for param in query.split("&"):
                        if "=" in param:
                            k, v = param.split("=", 1)
                            if k == "selfHash":
                                v = placeholder
                            params.append(f"{k}={v}")
                    vm["id"] = did_part + "?" + "&".join(params)
                else:
                    vm["id"] = replace_did_suffix(vm_id)


def verify_self_hash(jcs_str: str) -> str:
    """
    Verify the self-hash of a DID document and return the claimed digest.

    Steps:
    1. Parse and check all self-hash slots are equal (claimed_digest)
    2. Replace slots with placeholder
    3. JCS serialize
    4. BLAKE3 hash
    5. Compare

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
    if prefix != "E":
        raise SelfHashError(f"Unsupported hash function prefix: {prefix!r} (expected 'E' for BLAKE3)")

    if _is_placeholder(claimed):
        raise SelfHashError("Document has placeholder selfHash, not a real hash")

    doc_copy = copy.deepcopy(doc)
    _replace_self_hash_slots_in_place(doc_copy, BLAKE3_PLACEHOLDER)

    msg = _jcs_serialize(doc_copy)
    computed = "E" + _compute_blake3_base64url(msg)

    if computed != claimed:
        raise SelfHashError(
            f"Self-hash mismatch: computed {computed!r}, claimed {claimed!r}"
        )

    return claimed


def compute_self_hash(doc: dict[str, Any]) -> str:
    """
    Compute and return the self-hash for a document (with placeholder in slots).

    Mutates doc in place to fill in the hash. Use for creating test fixtures.
    """
    _replace_self_hash_slots_in_place(doc, BLAKE3_PLACEHOLDER)
    msg = _jcs_serialize(doc)
    digest = "E" + _compute_blake3_base64url(msg)
    _replace_self_hash_slots_in_place(doc, digest)
    return digest


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
