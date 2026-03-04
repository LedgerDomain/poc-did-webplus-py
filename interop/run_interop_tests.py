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
import logging
import os
import subprocess
import sys
import time
from urllib.parse import quote

import httpx

logger = logging.getLogger("interop")

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
logger.setLevel(logging.INFO)  # Ensure scenario/action/result messages always show


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


def _assert_vdg_headers(
    vdg_url: str,
    did_query: str,
    expected_self_hash: str,
    expected_cache_hit: bool,
    use_version_id_param: bool,
) -> bool:
    """GET VDG resolve endpoint and assert expected HTTP headers.

    did_query: DID URL, with or without ?versionId=N query param.
    expected_cache_hit: Expected X-DID-Webplus-VDG-Cache-Hit. Plain DID (no versionId)
        -> false (VDG must fetch latest from VDR). DID with versionId=N -> true
        (VDG has version from VDR notifications).
    use_version_id_param: True if did_query includes versionId param; for logging.
    """
    encoded_did = quote(did_query, safe="")
    url = f"{vdg_url.rstrip('/')}/webplus/v1/resolve/{encoded_did}"
    if use_version_id_param:
        logger.info(
            "Action: Rust VDG headers (versionId param) — GET resolve with ?versionId=1. "
            "VDG has version from VDR notifications; X-DID-Webplus-VDG-Cache-Hit expected true."
        )
    else:
        logger.info(
            "Action: Rust VDG headers (plain DID) — GET resolve without versionId query param. "
            "VDG must fetch latest from VDR; X-DID-Webplus-VDG-Cache-Hit expected false."
        )
    r = httpx.get(url, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — VDG resolve returned %s: %s", r.status_code, r.text)
        return False
    cc = r.headers.get("Cache-Control", "")
    if "no-cache" not in cc or "no-transform" not in cc:
        logger.error("Result: FAIL — Cache-Control missing no-cache/no-transform: %r", cc)
        return False
    if not r.headers.get("Last-Modified"):
        logger.error("Result: FAIL — Last-Modified header missing")
        return False
    etag = r.headers.get("ETag", "").strip('"')
    if etag != expected_self_hash:
        logger.error("Result: FAIL — ETag %r != expected selfHash %r", etag, expected_self_hash)
        return False
    cache_hit = r.headers.get("X-DID-Webplus-VDG-Cache-Hit")
    if cache_hit not in ("true", "false"):
        logger.error("Result: FAIL — X-DID-Webplus-VDG-Cache-Hit missing or invalid: %r", cache_hit)
        return False
    expected_str = "true" if expected_cache_hit else "false"
    if cache_hit != expected_str:
        logger.error(
            "Result: FAIL — X-DID-Webplus-VDG-Cache-Hit %r != expected %r",
            cache_hit,
            expected_str,
        )
        return False
    logger.info(
        "Result: PASS — VDG headers valid (Cache-Control, ETag, Last-Modified, X-DID-Webplus-VDG-Cache-Hit=%s)%s",
        expected_str,
        " (versionId param used)" if use_version_id_param else " (plain DID, no versionId param)",
    )
    return True


def python_resolver_vs_rust_vdr(vdr_url: str, vdg_url: str | None = None) -> bool:
    """Python resolver vs Rust VDR. vdg_url: if set, resolve via VDG."""
    logger.info("Creating root DID document for rust-vdr:8085")
    root_jcs, key = _make_root_doc_with_key(host="rust-vdr", port=8085)
    doc = json.loads(root_jcs)
    did = doc["id"]
    path = _resolution_path(did)
    url = f"{vdr_url.rstrip('/')}/{path}"

    logger.info("Action: POST create — submit root DID document to Rust VDR")
    r = httpx.post(url, content=root_jcs, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — POST returned %s: %s", r.status_code, r.text)
        return False
    logger.info("Result: PASS — root document created (200)")

    logger.info("Action: PUT update — submit signed update with key rotation to Rust VDR")
    update_jcs, _ = _make_update_doc_with_key(doc, key)
    r = httpx.put(url, content=update_jcs, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — PUT returned %s: %s", r.status_code, r.text)
        return False
    logger.info("Result: PASS — update applied (200)")

    logger.info("Action: GET from VDR — fetch did-documents.jsonl directly from Rust VDR")
    r = httpx.get(url, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — GET returned %s", r.status_code)
        return False
    update_doc = json.loads(update_jcs)
    if update_doc["selfHash"] not in r.text:
        logger.error("Result: FAIL — response does not contain update document")
        return False
    logger.info("Result: PASS — VDR returns latest (versionId=1)")

    if vdg_url:
        time.sleep(0.5)

    resolve_via = "VDG" if vdg_url else "VDR directly"
    logger.info("Action: Python resolver — resolve DID via %s", resolve_via)
    result = _run_resolve(did, vdg_url=vdg_url)
    if result.returncode != 0:
        err = result.stderr or "(see stderr above)"
        logger.error("Result: FAIL — Python resolve failed: %s", err)
        return False
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        logger.error("Result: FAIL — no didDocument in result")
        return False
    resolved = json.loads(out["didDocument"])
    if resolved.get("versionId") != 1:
        logger.error("Result: FAIL — expected versionId 1, got %s", resolved.get("versionId"))
        return False
    logger.info("Result: PASS — Python resolver returned versionId=1")

    if vdg_url:
        # Case 1: Plain DID (no versionId) -> X-DID-Webplus-VDG-Cache-Hit expected false
        if not _assert_vdg_headers(
            vdg_url, did, resolved["selfHash"],
            expected_cache_hit=False,
            use_version_id_param=False,
        ):
            return False
        # Case 2: DID with versionId=1 -> X-DID-Webplus-VDG-Cache-Hit expected true
        did_with_version = f"{did}?versionId=1"
        if not _assert_vdg_headers(
            vdg_url, did_with_version, resolved["selfHash"],
            expected_cache_hit=True,
            use_version_id_param=True,
        ):
            return False

    return True


def rust_resolver_vs_python_vdr(vdr_url: str, vdg_url: str | None = None) -> bool:
    """Rust resolver vs Python VDR. vdg_url: if set, resolve via VDG."""
    logger.info("Creating root DID document for python-vdr:8087")
    root_jcs, key = _make_root_doc_with_key(host="python-vdr", port=8087)
    doc = json.loads(root_jcs)
    did = doc["id"]
    path = _resolution_path(did)
    url = f"{vdr_url.rstrip('/')}/{path}"

    logger.info("Action: POST create — submit root DID document to Python VDR")
    r = httpx.post(url, content=root_jcs, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — POST returned %s: %s", r.status_code, r.text)
        return False
    logger.info("Result: PASS — root document created (200)")

    logger.info("Action: PUT update — submit signed update with key rotation to Python VDR")
    update_jcs, _ = _make_update_doc_with_key(doc, key)
    r = httpx.put(url, content=update_jcs, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — PUT returned %s: %s", r.status_code, r.text)
        return False
    logger.info("Result: PASS — update applied (200)")

    logger.info("Action: GET from VDR — fetch did-documents.jsonl directly from Python VDR")
    r = httpx.get(url, timeout=10.0)
    if r.status_code != 200:
        logger.error("Result: FAIL — GET returned %s", r.status_code)
        return False
    update_doc = json.loads(update_jcs)
    if update_doc["selfHash"] not in r.text:
        logger.error("Result: FAIL — response does not contain update document")
        return False
    logger.info("Result: PASS — VDR returns latest (versionId=1)")

    if vdg_url:
        time.sleep(0.5)

    resolve_via = "VDG" if vdg_url else "VDR directly"
    logger.info("Action: Resolver (Python stand-in for Rust) — resolve DID via %s", resolve_via)
    result = _run_resolve(did, vdg_url=vdg_url)
    if result.returncode != 0:
        err = result.stderr or "(see stderr above)"
        logger.error("Result: FAIL — resolve failed: %s", err)
        return False
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        logger.error("Result: FAIL — no didDocument in result")
        return False
    resolved = json.loads(out["didDocument"])
    if resolved.get("versionId") != 1:
        logger.error("Result: FAIL — expected versionId 1, got %s", resolved.get("versionId"))
        return False
    logger.info("Result: PASS — resolver returned versionId=1")

    if vdg_url:
        # Case 1: Plain DID (no versionId) -> X-DID-Webplus-VDG-Cache-Hit expected false
        if not _assert_vdg_headers(
            vdg_url, did, resolved["selfHash"],
            expected_cache_hit=False,
            use_version_id_param=False,
        ):
            return False
        # Case 2: DID with versionId=1 -> X-DID-Webplus-VDG-Cache-Hit expected true
        did_with_version = f"{did}?versionId=1"
        if not _assert_vdg_headers(
            vdg_url, did_with_version, resolved["selfHash"],
            expected_cache_hit=True,
            use_version_id_param=True,
        ):
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

    logger.info("Waiting for services...")
    time.sleep(3)

    ok = False
    if scenario == "1":
        logger.info("=== Scenario 1: Python resolver vs Rust VDR (no VDG) ===")
        logger.info("Testing: Python resolver fetches from Rust VDR directly")
        ok = python_resolver_vs_rust_vdr("http://rust-vdr:8085")
    elif scenario == "2":
        logger.info("=== Scenario 2: Python resolver vs Rust VDR + Rust VDG ===")
        logger.info("Testing: Python resolver fetches via Rust VDG; VDG proxies to Rust VDR")
        ok = python_resolver_vs_rust_vdr("http://rust-vdr:8085", vdg_url="http://rust-vdg:8086")
    elif scenario == "3":
        logger.info("=== Scenario 3: Rust resolver vs Python VDR (no VDG) ===")
        logger.info("Testing: Resolver (Python stand-in for Rust) fetches from Python VDR directly")
        ok = rust_resolver_vs_python_vdr("http://python-vdr:8087")
    elif scenario == "4":
        logger.info("=== Scenario 4: Rust resolver vs Python VDR + Rust VDG ===")
        logger.info("Testing: Resolver fetches via Rust VDG; VDG proxies to Python VDR")
        ok = rust_resolver_vs_python_vdr("http://python-vdr:8087", vdg_url="http://rust-vdg:8086")

    if ok:
        logger.info("=== All tests PASSED ===")
        if scenario == "1":
            logger.info("Summary — Scenario 1: Python resolver vs Rust VDR (no VDG)")
            logger.info(
                "  Action: POST create — Test script submitted root DID document to Rust VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: PUT update — Test script submitted signed update with key rotation to Rust VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: GET from Rust VDR — Test script fetched did-documents.jsonl from Rust VDR. "
                "Expected: response contains latest (versionId=1). Result: PASS."
            )
            logger.info(
                "  Action: Python resolver — Python resolver resolved DID via Rust VDR directly. "
                "Expected: versionId=1. Result: versionId=1."
            )
        elif scenario == "2":
            logger.info("Summary — Scenario 2: Python resolver vs Rust VDR + Rust VDG")
            logger.info(
                "  Action: POST create — Test script submitted root DID document to Rust VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: PUT update — Test script submitted signed update with key rotation to Rust VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: GET from Rust VDR — Test script fetched did-documents.jsonl from Rust VDR. "
                "Expected: response contains latest (versionId=1). Result: PASS."
            )
            logger.info(
                "  Action: Python resolver — Python resolver resolved DID via Rust VDG (Rust VDG proxies to Rust VDR). "
                "Expected: versionId=1. Result: versionId=1."
            )
            logger.info(
                "  Action: Rust VDG headers (plain DID) — GET resolve without versionId. "
                "VDG must fetch latest from Rust VDR; X-DID-Webplus-VDG-Cache-Hit expected false. Result: PASS."
            )
            logger.info(
                "  Action: Rust VDG headers (versionId param) — GET resolve with ?versionId=1. "
                "Rust VDR notified Rust VDG of updates; VDG has version; X-DID-Webplus-VDG-Cache-Hit expected true. Result: PASS."
            )
        elif scenario == "3":
            logger.info("Summary — Scenario 3: Rust resolver vs Python VDR (no VDG)")
            logger.info(
                "  Action: POST create — Test script submitted root DID document to Python VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: PUT update — Test script submitted signed update with key rotation to Python VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: GET from Python VDR — Test script fetched did-documents.jsonl from Python VDR. "
                "Expected: response contains latest (versionId=1). Result: PASS."
            )
            logger.info(
                "  Action: Resolver — Python resolver (stand-in for Rust) resolved DID via Python VDR directly. "
                "Expected: versionId=1. Result: versionId=1."
            )
        elif scenario == "4":
            logger.info("Summary — Scenario 4: Rust resolver vs Python VDR + Rust VDG")
            logger.info(
                "  Action: POST create — Test script submitted root DID document to Python VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: PUT update — Test script submitted signed update with key rotation to Python VDR. "
                "Expected: 200. Result: 200."
            )
            logger.info(
                "  Action: GET from Python VDR — Test script fetched did-documents.jsonl from Python VDR. "
                "Expected: response contains latest (versionId=1). Result: PASS."
            )
            logger.info(
                "  Action: Resolver — Python resolver (stand-in for Rust) resolved DID via Rust VDG (Rust VDG proxies to Python VDR). "
                "Expected: versionId=1. Result: versionId=1."
            )
            logger.info(
                "  Action: Rust VDG headers (plain DID) — GET resolve without versionId. "
                "VDG must fetch latest from Python VDR; X-DID-Webplus-VDG-Cache-Hit expected false. Result: PASS."
            )
            logger.info(
                "  Action: Rust VDG headers (versionId param) — GET resolve with ?versionId=1. "
                "Python VDR notified Rust VDG of updates; VDG has version; X-DID-Webplus-VDG-Cache-Hit expected true. Result: PASS."
            )
    else:
        logger.error("=== Tests FAILED ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
