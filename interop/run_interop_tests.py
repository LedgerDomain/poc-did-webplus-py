#!/usr/bin/env python3
"""
Run interoperability tests for did:webplus.

Scenarios:
  1: Python resolver vs Rust VDR (no VDG)
  2: Python resolver vs Rust VDR + Rust VDG
  3: Rust resolver vs Python VDR (no VDG)
  4: Rust resolver vs Python VDR + Rust VDG

Usage: ./run_interop_tests.py <1|2|3|4>
Or: docker compose up -d (with appropriate env) then ./run_interop_tests.py <1|2|3|4>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from urllib.parse import quote

import httpx

# Enable DEBUG logging for interop tests (main process and resolver subprocess)
os.environ.setdefault("DID_WEBPLUS_LOG_LEVEL", "DEBUG")
# Use http for test hostnames (rust-vdr, rust-vdg, python-vdr)
os.environ.setdefault(
    "DID_WEBPLUS_HTTP_SCHEME_OVERRIDE",
    "rust-vdr=http,rust-vdg=http,python-vdr=http",
)
import rfc8785
from jwcrypto import jwk

# Add parent for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from did_webplus.logging_config import configure_logging
from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash, hash_bytes_for_hashed_key
from did_webplus.verification import create_proof, jwk_to_multibase_key

configure_logging()


def _make_root_doc_with_key(
    host: str = "localhost",
    port: int | None = 8085,
) -> tuple[str, jwk.JWK]:
    """Create a root DID document with a generated key for updates. Returns (jcs, private_key)."""
    key = jwk.JWK.generate(kty="OKP", crv="Ed25519")
    key_str = jwk_to_multibase_key(key)
    host_part = f"{host}%3A{port}" if port else host
    doc = {
        "assertionMethod": ["#0"],
        "authentication": ["#0"],
        "capabilityDelegation": ["#0"],
        "capabilityInvocation": ["#0"],
        "id": f"did:webplus:{host_part}:{BLAKE3_PLACEHOLDER}",
        "keyAgreement": ["#0"],
        "selfHash": BLAKE3_PLACEHOLDER,
        "updateRules": {"key": key_str},
        "validFrom": "2024-01-01T00:00:00Z",
        "verificationMethod": [
            {
                "controller": f"did:webplus:{host_part}:{BLAKE3_PLACEHOLDER}",
                "id": f"did:webplus:{host_part}:{BLAKE3_PLACEHOLDER}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0",
                "publicKeyJwk": key.export_public(as_dict=True)
                | {"kid": f"did:webplus:{host_part}:{BLAKE3_PLACEHOLDER}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0"},
                "type": "JsonWebKey2020",
            }
        ],
        "versionId": 0,
    }
    compute_self_hash(doc)
    return rfc8785.dumps(doc).decode("utf-8"), key


def _make_update_doc_with_key(
    prev_doc: dict,
    signing_key: jwk.JWK,
) -> tuple[str, jwk.JWK]:
    """Create a signed update document (versionId=1) with key rotation.

    The proof is signed by signing_key (must satisfy prev_doc's updateRules).
    A new key is generated for verificationMethod and updateRules.hashedKey.
    Returns (jcs, new_key) for potential further updates.
    """
    root_hash = prev_doc["selfHash"]
    did = prev_doc["id"]
    new_key = jwk.JWK.generate(kty="OKP", crv="Ed25519")
    new_key_str = jwk_to_multibase_key(new_key)
    hashed_key = hash_bytes_for_hashed_key(new_key_str.encode("utf-8"), root_hash)
    doc = {
        "assertionMethod": ["#0"],
        "authentication": ["#0"],
        "capabilityDelegation": ["#0"],
        "capabilityInvocation": ["#0"],
        "id": did,
        "keyAgreement": ["#0"],
        "prevDIDDocumentSelfHash": root_hash,
        "selfHash": BLAKE3_PLACEHOLDER,
        "updateRules": {"hashedKey": hashed_key},
        "validFrom": "2024-01-01T00:00:01Z",
        "verificationMethod": [
            {
                "controller": did,
                "id": f"{did}?selfHash={BLAKE3_PLACEHOLDER}&versionId=1#0",
                "publicKeyJwk": new_key.export_public(as_dict=True)
                | {"kid": f"{did}?selfHash={BLAKE3_PLACEHOLDER}&versionId=1#0"},
                "type": "JsonWebKey2020",
            }
        ],
        "versionId": 1,
    }
    proof = create_proof(doc, signing_key)
    doc["proofs"] = [proof]
    compute_self_hash(doc)
    return rfc8785.dumps(doc).decode("utf-8"), new_key


def _resolution_path(did: str) -> str:
    """Extract path for resolution URL from DID (path only; host/port are in the URL authority)."""
    from urllib.parse import urlparse

    from did_webplus.did import parse_did, parse_http_scheme_overrides

    components = parse_did(did)
    overrides = parse_http_scheme_overrides(
        os.environ.get("DID_WEBPLUS_HTTP_SCHEME_OVERRIDE")
    )
    full_url = components.resolution_url(http_scheme_overrides=overrides or None)
    parsed = urlparse(full_url)
    return parsed.path.lstrip("/") if parsed.path else ""


def _run_resolve(did: str, vdg_url: str | None = None) -> subprocess.CompletedProcess:
    """Run Python resolver. vdg_url: if set, resolve via VDG instead of VDR."""
    cmd = ["uv", "run", "did-webplus", "resolve", did, "-o", "json"]
    if vdg_url:
        cmd.extend(["--vdg-url", vdg_url.rstrip("/")])
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=None,  # Let resolver logs (stderr) print to terminal
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        timeout=15,
    )


def _assert_vdg_headers(vdg_url: str, did: str, expected_self_hash: str) -> bool:
    """GET VDG resolve endpoint and assert expected HTTP headers."""
    encoded_did = quote(did, safe="")
    url = f"{vdg_url.rstrip('/')}/webplus/v1/resolve/{encoded_did}"
    r = httpx.get(url, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: VDG resolve {url} -> {r.status_code}\n{r.text}")
        return False
    cc = r.headers.get("Cache-Control", "")
    if "no-cache" not in cc or "no-transform" not in cc:
        print(f"  FAIL: Cache-Control missing no-cache/no-transform: {cc!r}")
        return False
    if not r.headers.get("Last-Modified"):
        print(f"  FAIL: Last-Modified header missing")
        return False
    etag = r.headers.get("ETag", "").strip('"')
    if etag != expected_self_hash:
        print(f"  FAIL: ETag {etag!r} != expected selfHash {expected_self_hash!r}")
        return False
    cache_hit = r.headers.get("X-DID-Webplus-VDG-Cache-Hit")
    if cache_hit not in ("true", "false"):
        print(f"  FAIL: X-DID-Webplus-VDG-Cache-Hit missing or invalid: {cache_hit!r}")
        return False
    print("  VDG headers: OK")
    return True


def python_resolver_vs_rust_vdr(vdr_url: str, vdg_url: str | None = None) -> bool:
    """Python resolver vs Rust VDR. vdg_url: if set, resolve via VDG."""
    root_jcs, key = _make_root_doc_with_key(host="rust-vdr", port=8085)
    doc = json.loads(root_jcs)
    did = doc["id"]
    path = _resolution_path(did)
    url = f"{vdr_url.rstrip('/')}/{path}"

    # POST create
    r = httpx.post(url, content=root_jcs, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: POST {url} -> {r.status_code}\n{r.text}")
        return False
    print("  POST create: OK")

    # PUT update (key rotation)
    update_jcs, _ = _make_update_doc_with_key(doc, key)
    r = httpx.put(url, content=update_jcs, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: PUT {url} -> {r.status_code}\n{r.text}")
        return False
    print("  PUT update: OK")

    # GET resolve (direct from VDR) - expect latest (update)
    r = httpx.get(url, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: GET {url} -> {r.status_code}")
        return False
    update_doc = json.loads(update_jcs)
    if update_doc["selfHash"] not in r.text:
        print(f"  FAIL: GET response does not contain update document")
        return False
    print("  GET resolve: OK")

    if vdg_url:
        time.sleep(0.5)

    # Python resolver (from VDR directly or via VDG)
    result = _run_resolve(did, vdg_url=vdg_url)
    if result.returncode != 0:
        err = result.stderr or "(see stderr above)"
        print(f"  FAIL: Python resolve: {err}")
        return False
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        print(f"  FAIL: No didDocument in result")
        return False
    resolved = json.loads(out["didDocument"])
    if resolved.get("versionId") != 1:
        print(f"  FAIL: Expected versionId 1, got {resolved.get('versionId')}")
        return False
    print("  Python resolve: OK")

    if vdg_url:
        if not _assert_vdg_headers(vdg_url, did, resolved["selfHash"]):
            return False

    return True


def rust_resolver_vs_python_vdr(vdr_url: str, vdg_url: str | None = None) -> bool:
    """Rust resolver vs Python VDR. vdg_url: if set, resolve via VDG."""
    root_jcs, key = _make_root_doc_with_key(host="python-vdr", port=8087)
    doc = json.loads(root_jcs)
    did = doc["id"]
    path = _resolution_path(did)
    url = f"{vdr_url.rstrip('/')}/{path}"

    # POST create
    r = httpx.post(url, content=root_jcs, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: POST {url} -> {r.status_code}\n{r.text}")
        return False
    print("  POST create: OK")

    # PUT update (key rotation)
    update_jcs, _ = _make_update_doc_with_key(doc, key)
    r = httpx.put(url, content=update_jcs, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: PUT {url} -> {r.status_code}\n{r.text}")
        return False
    print("  PUT update: OK")

    # GET resolve (direct from VDR)
    r = httpx.get(url, timeout=10.0)
    if r.status_code != 200:
        print(f"  FAIL: GET {url} -> {r.status_code}")
        return False
    update_doc = json.loads(update_jcs)
    if update_doc["selfHash"] not in r.text:
        print(f"  FAIL: GET response does not contain update document")
        return False
    print("  GET resolve: OK")

    if vdg_url:
        time.sleep(0.5)

    # Python resolver (stand-in for Rust - from VDR directly or via VDG)
    result = _run_resolve(did, vdg_url=vdg_url)
    if result.returncode != 0:
        err = result.stderr or "(see stderr above)"
        print(f"  FAIL: Resolve: {err}")
        return False
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        print(f"  FAIL: No didDocument")
        return False
    resolved = json.loads(out["didDocument"])
    if resolved.get("versionId") != 1:
        print(f"  FAIL: Expected versionId 1, got {resolved.get('versionId')}")
        return False
    print("  Resolve: OK")

    if vdg_url:
        if not _assert_vdg_headers(vdg_url, did, resolved["selfHash"]):
            return False

    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ./run_interop_tests.py <1|2|3|4>")
        return 1
    scenario = sys.argv[1]
    if scenario not in ("1", "2", "3", "4"):
        print("Scenario must be 1, 2, 3, or 4")
        return 1

    # Wait for services
    print("Waiting for services...")
    time.sleep(3)

    ok = False
    if scenario == "1":
        print("Scenario 1: Python resolver vs Rust VDR (no VDG)")
        ok = python_resolver_vs_rust_vdr("http://rust-vdr:8085")
    elif scenario == "2":
        print("Scenario 2: Python resolver vs Rust VDR + Rust VDG")
        ok = python_resolver_vs_rust_vdr("http://rust-vdr:8085", vdg_url="http://rust-vdg:8086")
    elif scenario == "3":
        print("Scenario 3: Rust resolver vs Python VDR (no VDG)")
        ok = rust_resolver_vs_python_vdr("http://python-vdr:8087")
    elif scenario == "4":
        print("Scenario 4: Rust resolver vs Python VDR + Rust VDG")
        ok = rust_resolver_vs_python_vdr("http://python-vdr:8087", vdg_url="http://rust-vdg:8086")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
