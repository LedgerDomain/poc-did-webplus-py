"""DID controller for did:webplus: create, update, deactivate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import rfc8785
from jwcrypto import jwk

from did_webplus.did import (
    MalformedDIDError,
    VDRURLComponents,
    did_to_resolution_url,
    parse_did,
    parse_vdr_url,
    resolution_path,
)
from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash
from did_webplus.verification import create_proof, jwk_to_multibase_key


def _valid_from_now() -> str:
    """Return validFrom timestamp with millisecond precision, no trailing zeros in fractional part."""
    dt = datetime.now(timezone.utc)
    ms = dt.microsecond // 1000
    frac = str(ms).rstrip("0") if ms else ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + (f".{frac}Z" if frac else "Z")


class ControllerError(Exception):
    """DID controller operation failed."""


def _key_path(base_dir: Path, did: str) -> Path:
    """Path to the private key file for a DID. Subdir is the DID itself."""
    return base_dir / did / "privkey.json"


def load_key(base_dir: Path, did: str) -> jwk.JWK:
    """Load and parse JWK from the key file for a DID."""
    path = _key_path(base_dir, did)
    if not path.exists():
        raise ControllerError(f"No key found for DID {did}")
    try:
        data = path.read_text()
        return jwk.JWK.from_json(data)
    except Exception as e:
        raise ControllerError(f"Failed to load key for {did}: {e}") from e


def save_key(base_dir: Path, did: str, key: jwk.JWK, *, kid: str) -> None:
    """Write JWK JSON to the key file for a DID, with kid set for signing."""
    path = _key_path(base_dir, did)
    path.parent.mkdir(parents=True, exist_ok=True)
    key_dict = json.loads(key.export(private_key=True))
    key_dict["kid"] = kid
    path.write_text(json.dumps(key_dict))


def _build_root_doc(
    vdr_components: VDRURLComponents,
    key: jwk.JWK,
) -> dict:
    """Build root DID document with placeholder for selfHash."""
    host_part = vdr_components.host_part_for_did()
    parts = [f"did:webplus:{host_part}"]
    if vdr_components.path:
        parts.append(vdr_components.path)
    parts.append(BLAKE3_PLACEHOLDER)
    did_placeholder = ":".join(parts)
    vm_id = f"{did_placeholder}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0"
    pub_jwk = key.export_public(as_dict=True) | {"kid": vm_id}
    return {
        "assertionMethod": ["#0"],
        "authentication": ["#0"],
        "capabilityDelegation": ["#0"],
        "capabilityInvocation": ["#0"],
        "id": did_placeholder,
        "keyAgreement": ["#0"],
        "selfHash": BLAKE3_PLACEHOLDER,
        "updateRules": {"key": jwk_to_multibase_key(key)},
        "validFrom": _valid_from_now(),
        "verificationMethod": [
            {
                "controller": did_placeholder,
                "id": vm_id,
                "publicKeyJwk": pub_jwk,
                "type": "JsonWebKey2020",
            }
        ],
        "versionId": 0,
    }


def create_did(
    vdr_did_create_endpoint: str,
    base_dir: Path,
    *,
    http_scheme_overrides: dict[str, str] | None = None,
) -> str:
    """
    Create a new DID: generate key in memory, build root doc, POST to VDR.
    Save key to base_dir only after POST succeeds (no temp directory).

    Returns the created DID.
    """
    try:
        vdr_components = parse_vdr_url(vdr_did_create_endpoint)
    except MalformedDIDError as e:
        raise ControllerError(str(e)) from e

    key = jwk.JWK.generate(kty="OKP", crv="Ed25519")
    doc = _build_root_doc(vdr_components, key)
    compute_self_hash(doc)
    did = doc["id"]
    jcs_str = rfc8785.dumps(doc).decode("utf-8")

    path = resolution_path(did)
    post_url = f"{vdr_did_create_endpoint.rstrip('/')}/{path}"

    with httpx.Client() as client:
        resp = client.post(post_url, content=jcs_str)
    if resp.status_code != 200:
        raise ControllerError(
            f"VDR POST failed: {resp.status_code} {resp.text!r}"
        )

    kid = f"{did}?selfHash={doc['selfHash']}&versionId=0#0"
    save_key(base_dir, did, key, kid=kid)
    return did


def _fetch_microledger(
    did: str,
    *,
    http_scheme_overrides: dict[str, str] | None = None,
) -> str:
    """Fetch full microledger (did-documents.jsonl) from VDR."""
    url = did_to_resolution_url(did, http_scheme_overrides=http_scheme_overrides)
    with httpx.Client() as client:
        resp = client.get(url)
    if resp.status_code != 200:
        raise ControllerError(f"VDR GET failed: {resp.status_code} {resp.text!r}")
    return resp.text


def _last_document_from_jsonl(jsonl: str) -> dict:
    """Parse JSONL and return the last document."""
    lines = [l.strip() for l in jsonl.strip().split("\n") if l.strip()]
    if not lines:
        raise ControllerError("Microledger is empty")
    return json.loads(lines[-1])


def _build_update_doc(
    prev_doc: dict,
    new_key: jwk.JWK | None,
    signing_key: jwk.JWK,
    *,
    deactivate: bool = False,
) -> dict:
    """Build update or deactivation document."""
    did = prev_doc["id"]
    prev_hash = prev_doc["selfHash"]
    version_id = prev_doc["versionId"] + 1

    if deactivate:
        doc = {
            "assertionMethod": [],
            "authentication": [],
            "capabilityDelegation": [],
            "capabilityInvocation": [],
            "id": did,
            "keyAgreement": [],
            "prevDIDDocumentSelfHash": prev_hash,
            "selfHash": BLAKE3_PLACEHOLDER,
            "updateRules": {},
            "validFrom": _valid_from_now(),
            "verificationMethod": [],
            "versionId": version_id,
        }
    else:
        assert new_key is not None
        vm_id = f"{did}?selfHash={BLAKE3_PLACEHOLDER}&versionId={version_id}#0"
        pub_jwk = new_key.export_public(as_dict=True) | {"kid": vm_id}
        doc = {
            "assertionMethod": ["#0"],
            "authentication": ["#0"],
            "capabilityDelegation": ["#0"],
            "capabilityInvocation": ["#0"],
            "id": did,
            "keyAgreement": ["#0"],
            "prevDIDDocumentSelfHash": prev_hash,
            "selfHash": BLAKE3_PLACEHOLDER,
            "updateRules": {"key": jwk_to_multibase_key(new_key)},
            "validFrom": _valid_from_now(),
            "verificationMethod": [
                {
                    "controller": did,
                    "id": vm_id,
                    "publicKeyJwk": pub_jwk,
                    "type": "JsonWebKey2020",
                }
            ],
            "versionId": version_id,
        }

    proof = create_proof(doc, signing_key)
    doc["proofs"] = [proof]
    compute_self_hash(doc)
    return doc


def update_did(
    did: str,
    base_dir: Path,
    *,
    http_scheme_overrides: dict[str, str] | None = None,
) -> None:
    """
    Update a DID: load key, fetch latest, generate new key, build update doc,
    PUT to VDR, replace key on success.
    """
    parse_did(did)
    key = load_key(base_dir, did)
    jsonl = _fetch_microledger(did, http_scheme_overrides=http_scheme_overrides)
    prev_doc = _last_document_from_jsonl(jsonl)
    new_key = jwk.JWK.generate(kty="OKP", crv="Ed25519")
    doc = _build_update_doc(prev_doc, new_key, key, deactivate=False)
    jcs_str = rfc8785.dumps(doc).decode("utf-8")

    url = did_to_resolution_url(did, http_scheme_overrides=http_scheme_overrides)
    with httpx.Client() as client:
        resp = client.put(url, content=jcs_str)
    if resp.status_code != 200:
        raise ControllerError(f"VDR PUT failed: {resp.status_code} {resp.text!r}")

    _key_path(base_dir, did).unlink()
    kid = f"{did}?selfHash={doc['selfHash']}&versionId={doc['versionId']}#0"
    save_key(base_dir, did, new_key, kid=kid)


def deactivate_did(
    did: str,
    base_dir: Path,
    *,
    http_scheme_overrides: dict[str, str] | None = None,
) -> None:
    """
    Deactivate a DID: build deactivation doc (empty verificationMethod, updateRules),
    sign with current key, PUT to VDR, delete key on success.
    """
    parse_did(did)
    key = load_key(base_dir, did)
    jsonl = _fetch_microledger(did, http_scheme_overrides=http_scheme_overrides)
    prev_doc = _last_document_from_jsonl(jsonl)
    doc = _build_update_doc(prev_doc, None, key, deactivate=True)
    jcs_str = rfc8785.dumps(doc).decode("utf-8")

    url = did_to_resolution_url(did, http_scheme_overrides=http_scheme_overrides)
    with httpx.Client() as client:
        resp = client.put(url, content=jcs_str)
    if resp.status_code != 200:
        raise ControllerError(f"VDR PUT failed: {resp.status_code} {resp.text!r}")

    _key_path(base_dir, did).unlink()
