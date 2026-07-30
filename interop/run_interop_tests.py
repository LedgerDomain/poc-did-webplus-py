#!/usr/bin/env python3
"""
Run interoperability tests for did:webplus.

Scenarios 1–16: 4 binary axes — Controller (Python/Rust), VDR (Python/Rust),
Resolver (Python/Rust), VDG (no/yes). Create/update/deactivate via the chosen
controller CLI; resolution via the chosen resolver.

Scenarios 17–20: TS (@zkred/did-webplus) resolver under test with reference
Python/Rust controller + VDR full lifecycle (create → v0 → update → v1 →
deactivate → v2), with optional VDG header checks.

Scenarios 21–22: TS controller full lifecycle (create → v0 → update → v1 →
deactivate → v2); both Python and Rust resolvers verify the same DID.
VDG omitted.

Usage: ./run_interop_tests.py <1-22>
Or: docker compose up -d (with appropriate env) then ./run_interop_tests.py <1-22>
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

INTEROP_DIR = Path(__file__).resolve().parent
from urllib.parse import quote, urlparse

import httpx

from resolvers import (
    HTTP_SCHEME_OVERRIDE,
    RUST_CLI_IMAGE,
    ZKRED_IMAGE,
    _run_python_resolve,
    _run_rust_resolve,
    _run_zkred_resolve,
)

PACKAGE_LOCK_PATH = INTEROP_DIR / "package-lock.json"
ZKRED_LOCKFILE_KEY = "node_modules/@zkred/did-webplus"

# VDR base URLs and create endpoints
RUST_VDR_URL = "http://rust-vdr:8085"
PYTHON_VDR_URL = "http://python-vdr:8087"
VDG_URL = "http://rust-vdg:8086"

logger = logging.getLogger("interop")

# Enable DEBUG logging for interop tests (main process and resolver subprocess)
os.environ.setdefault("DID_WEBPLUS_LOG_LEVEL", "DEBUG")
# Use http for test hostnames (rust-vdr, rust-vdg, python-vdr, ledgerdomain.github.io)
os.environ.setdefault("DID_WEBPLUS_HTTP_SCHEME_OVERRIDE", HTTP_SCHEME_OVERRIDE)

# Add parent for imports
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)
from did_webplus.logging_config import configure_logging
from did_webplus.did import parse_did, parse_http_scheme_overrides

configure_logging()
logger.setLevel(logging.INFO)  # Ensure scenario/action/result messages always show


def _run_python_controller_create(vdr_create_endpoint: str, wallet_dir: Path) -> str:
    """Run Python controller create; return created DID from stdout."""
    cmd = [
        "uv", "run", "did-webplus", "did", "create", vdr_create_endpoint,
        "--base-dir", str(wallet_dir),
        "--http-scheme-override", HTTP_SCHEME_OVERRIDE,
    ]
    logger.info("Action: Python controller create — %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Python create: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Python controller create failed: {result.stderr or result.stdout}")
    did = result.stdout.strip()
    if not did.startswith("did:webplus:"):
        logger.error("Result: FAIL — unexpected stdout: %r", result.stdout)
        raise RuntimeError(f"Python controller create did not output a DID: {result.stdout!r}")
    logger.info("Result: PASS — created %s", did)
    return did


def _run_python_controller_update(did: str, wallet_dir: Path) -> None:
    """Run Python controller update."""
    cmd = [
        "uv", "run", "did-webplus", "did", "update", did,
        "--base-dir", str(wallet_dir),
        "--http-scheme-override", HTTP_SCHEME_OVERRIDE,
    ]
    logger.info("Action: Python controller update — did update %s", did)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Python update: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Python controller update failed: {result.stderr or result.stdout}")
    logger.info("Result: PASS — update applied")


DEACTIVATE_CONFIRM = "THIS-IS-IRREVERSIBLE"


def _run_python_controller_deactivate(did: str, wallet_dir: Path) -> None:
    """Run Python controller deactivate (requires --confirm THIS-IS-IRREVERSIBLE)."""
    cmd = [
        "uv", "run", "did-webplus", "did", "deactivate", did,
        "--confirm", DEACTIVATE_CONFIRM,
        "--base-dir", str(wallet_dir),
        "--http-scheme-override", HTTP_SCHEME_OVERRIDE,
    ]
    logger.info("Action: Python controller deactivate — did deactivate %s", did)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Python deactivate: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Python controller deactivate failed: {result.stderr or result.stdout}")
    logger.info("Result: PASS — deactivate applied")


def _run_rust_controller_create(vdr_create_endpoint: str, wallet_dir: Path) -> str:
    """Run Rust controller create via Docker; return created DID from stdout."""
    cmd = [
        "docker", "run", "--rm",
        "--network", "host",
        "-e", f"DID_WEBPLUS_HTTP_SCHEME_OVERRIDE={HTTP_SCHEME_OVERRIDE}",
        "-v", f"{wallet_dir.resolve()}:/root/.did-webplus",
        RUST_CLI_IMAGE,
        "wallet", "did", "create", "--vdr", vdr_create_endpoint,
    ]
    logger.info("Action: Rust controller create — wallet did create --vdr %s", vdr_create_endpoint)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Rust create: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Rust controller create failed: {result.stderr or result.stdout}")
    # Parse DID from stdout (e.g. last line or line containing did:webplus:)
    for line in reversed(result.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("did:webplus:"):
            logger.info("Result: PASS — created %s", line)
            return line
    logger.error("Result: FAIL — no DID in stdout: %r", result.stdout)
    raise RuntimeError(f"Rust controller create did not output a DID: {result.stdout!r}")


def _run_rust_controller_update(wallet_dir: Path, did: str) -> None:
    """Run Rust controller update via Docker; pass --did <base DID> (no query or fragment)."""
    base_did = did.split("?")[0]
    cmd = [
        "docker", "run", "--rm",
        "--network", "host",
        "-e", f"DID_WEBPLUS_HTTP_SCHEME_OVERRIDE={HTTP_SCHEME_OVERRIDE}",
        "-v", f"{wallet_dir.resolve()}:/root/.did-webplus",
        RUST_CLI_IMAGE,
        "wallet", "did", "update", "--did", base_did,
    ]
    logger.info("Action: Rust controller update — wallet did update --did %s", base_did)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Rust update: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Rust controller update failed: {result.stderr or result.stdout}")
    logger.info("Result: PASS — update applied")


def _run_rust_controller_deactivate(wallet_dir: Path, did: str) -> None:
    """Run Rust controller deactivate via Docker (requires --confirm THIS-IS-IRREVERSIBLE)."""
    base_did = did.split("?")[0]
    cmd = [
        "docker", "run", "--rm",
        "--network", "host",
        "-e", f"DID_WEBPLUS_HTTP_SCHEME_OVERRIDE={HTTP_SCHEME_OVERRIDE}",
        "-v", f"{wallet_dir.resolve()}:/root/.did-webplus",
        RUST_CLI_IMAGE,
        "wallet", "did", "deactivate", "--did", base_did, "--confirm", DEACTIVATE_CONFIRM,
    ]
    logger.info("Action: Rust controller deactivate — wallet did deactivate --did %s", base_did)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Rust deactivate: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Rust controller deactivate failed: {result.stderr or result.stdout}")
    logger.info("Result: PASS — deactivate applied")


def _resolution_path(did: str) -> str:
    """Extract path for resolution URL from DID (path only; host/port are in the URL authority)."""
    components = parse_did(did)
    overrides = parse_http_scheme_overrides(
        os.environ.get("DID_WEBPLUS_HTTP_SCHEME_OVERRIDE")
    )
    full_url = components.resolution_url(http_scheme_overrides=overrides or None)
    parsed = urlparse(full_url)
    return parsed.path.lstrip("/") if parsed.path else ""


def _zkred_controller_cmd(args: list[str], wallet_dir: Path) -> tuple[list[str], str | None]:
    """Build zkred controller docker/local command; mount wallet_dir for Docker.

    Returns (cmd, cwd). Docker mounts the host wallet at ``/wallet`` and expects
    ``args`` to already include ``--wallet-dir /wallet``; local mode uses the
    host path in ``args`` and runs ``node`` under ``INTEROP_DIR``.
    """
    wallet_dir = wallet_dir.resolve()
    if os.environ.get("INTEROP_ZKRED_LOCAL"):
        cmd = ["node", str(INTEROP_DIR / "ts_runner.mjs"), *args]
        return cmd, str(INTEROP_DIR)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{wallet_dir}:/wallet",
        ZKRED_IMAGE,
        *args,
    ]
    return cmd, None


def _run_zkred_controller_create(vdr_url: str, wallet_dir: Path) -> str:
    """Run Zkred/TS controller create; return created DID from stdout."""
    wallet_dir = wallet_dir.resolve()
    if os.environ.get("INTEROP_ZKRED_LOCAL"):
        wallet_arg = str(wallet_dir)
    else:
        wallet_arg = "/wallet"
    args = [
        "controller", "create",
        "--vdr-url", vdr_url,
        "--wallet-dir", wallet_arg,
    ]
    cmd, cwd = _zkred_controller_cmd(args, wallet_dir)
    logger.info("Action: Zkred/TS controller create — %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Zkred/TS create: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Zkred/TS controller create failed: {result.stderr or result.stdout}")
    did = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""
    if not did.startswith("did:webplus:"):
        logger.error("Result: FAIL — unexpected stdout: %r", result.stdout)
        raise RuntimeError(f"Zkred/TS controller create did not output a DID: {result.stdout!r}")
    logger.info("Result: PASS — created %s", did)
    return did


def _run_zkred_controller_update(did: str, wallet_dir: Path) -> None:
    """Run Zkred/TS controller update via Docker (or local node)."""
    base_did = did.split("?")[0]
    wallet_dir = wallet_dir.resolve()
    if os.environ.get("INTEROP_ZKRED_LOCAL"):
        wallet_arg = str(wallet_dir)
    else:
        wallet_arg = "/wallet"
    args = [
        "controller", "update",
        "--did", base_did,
        "--wallet-dir", wallet_arg,
    ]
    cmd, cwd = _zkred_controller_cmd(args, wallet_dir)
    logger.info("Action: Zkred/TS controller update — controller update --did %s", base_did)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Zkred/TS update: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Zkred/TS controller update failed: {result.stderr or result.stdout}")
    logger.info("Result: PASS — update applied")


def _run_zkred_controller_deactivate(did: str, wallet_dir: Path) -> None:
    """Run Zkred/TS controller deactivate via Docker (or local node)."""
    base_did = did.split("?")[0]
    wallet_dir = wallet_dir.resolve()
    if os.environ.get("INTEROP_ZKRED_LOCAL"):
        wallet_arg = str(wallet_dir)
    else:
        wallet_arg = "/wallet"
    args = [
        "controller", "deactivate",
        "--did", base_did,
        "--wallet-dir", wallet_arg,
    ]
    cmd, cwd = _zkred_controller_cmd(args, wallet_dir)
    logger.info("Action: Zkred/TS controller deactivate — controller deactivate --did %s", base_did)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("Result: FAIL — Zkred/TS deactivate: %s", result.stderr or result.stdout)
        raise RuntimeError(f"Zkred/TS controller deactivate failed: {result.stderr or result.stdout}")
    logger.info("Result: PASS — deactivate applied")


def _resolver_display_name(resolver_kind: str) -> str:
    """Human-readable resolver name for logs."""
    return {
        "python": "Python",
        "rust": "Rust",
        "zkred": "Zkred/TS",
        "both": "Python and Rust",
    }.get(resolver_kind, resolver_kind.capitalize())


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


def _scenario_params(n: int) -> tuple[str, str, str, bool]:
    """Map scenario number to (controller_kind, vdr_kind, resolver_kind, use_vdg).

    1–16: existing 4-bit mapping (unchanged).
    17–22: TS-specific mapping via ``_ts_scenario_params``.
    """
    if 17 <= n <= 22:
        return _ts_scenario_params(n)
    n0 = n - 1
    controller = "rust" if (n0 & 8) else "python"
    vdr = "rust" if (n0 & 4) else "python"
    resolver = "rust" if (n0 & 2) else "python"
    use_vdg = bool(n0 & 1)
    return controller, vdr, resolver, use_vdg


def _ts_scenario_params(n: int) -> tuple[str, str, str, bool]:
    """Map scenario number 17–22 to (controller_kind, vdr_kind, resolver_kind, use_vdg).

    17–20: reference controller + matching VDR; TS (zkred) resolver; VDG on/off.
    21–22: TS controller + VDR; resolver_kind "both" means dual Python+Rust
    verification after create (v0), update (v1), and deactivate (v2); use_vdg=False.
    """
    mapping = {
        17: ("python", "python", "zkred", False),
        18: ("python", "python", "zkred", True),
        19: ("rust", "rust", "zkred", False),
        20: ("rust", "rust", "zkred", True),
        21: ("zkred", "python", "both", False),
        22: ("zkred", "rust", "both", False),
    }
    if n not in mapping:
        raise ValueError(f"TS scenario must be 17-22, got {n}")
    return mapping[n]


def _run_resolve_and_assert(
    did: str,
    resolver_kind: str,
    vdg_url: str | None,
    expected_version_id: int,
) -> tuple[bool, str | None]:
    """Run chosen resolver, assert versionId. Returns (ok, resolved_self_hash or None)."""
    if resolver_kind == "python":
        result = _run_python_resolve(did, vdg_url=vdg_url)
    elif resolver_kind == "zkred":
        result = _run_zkred_resolve(did, vdg_url=vdg_url)
    else:
        result = _run_rust_resolve(did, vdg_url=vdg_url)
    resolver_name = _resolver_display_name(resolver_kind)
    if result.returncode != 0:
        logger.error("Result: FAIL — %s resolve failed: %s", resolver_name, result.stderr or "(see stderr)")
        return False, None
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        logger.error("Result: FAIL — no didDocument in result")
        return False, None
    doc = out["didDocument"]
    resolved = json.loads(doc) if isinstance(doc, str) else doc
    vid = resolved.get("versionId")
    if vid != expected_version_id:
        logger.error("Result: FAIL — expected versionId %s, got %s", expected_version_id, vid)
        return False, None
    logger.info("Result: PASS — %s resolver returned versionId=%s", resolver_name, expected_version_id)
    return True, resolved.get("selfHash")


def _run_both_reference_resolvers_and_assert(
    did: str,
    vdg_url: str | None,
    expected_version_id: int,
) -> tuple[bool, str | None]:
    """Run Python then Rust resolver on the same DID; both must assert versionId.

    Used by scenarios 21–22 (TS controller) for cross-implementation read checks.
    Returns (ok, self_hash from the last successful resolve, or None).
    """
    ok, self_hash = _run_resolve_and_assert(did, "python", vdg_url, expected_version_id)
    if not ok:
        return False, None
    ok, self_hash = _run_resolve_and_assert(did, "rust", vdg_url, expected_version_id)
    if not ok:
        return False, None
    return True, self_hash


def _run_resolve_and_assert_deactivated(
    did: str,
    resolver_kind: str,
    vdg_url: str | None,
    expected_version_id: int = 2,
) -> bool:
    """Run chosen resolver, assert document is deactivated: updateRules {}, all key arrays []. Returns True iff all checks pass."""
    if resolver_kind == "python":
        result = _run_python_resolve(did, vdg_url=vdg_url)
    elif resolver_kind == "zkred":
        result = _run_zkred_resolve(did, vdg_url=vdg_url)
    else:
        result = _run_rust_resolve(did, vdg_url=vdg_url)
    resolver_name = _resolver_display_name(resolver_kind)
    if result.returncode != 0:
        logger.error("Result: FAIL — %s resolve failed (after deactivate): %s", resolver_name, result.stderr or "(see stderr)")
        return False
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        logger.error("Result: FAIL — no didDocument in result (after deactivate)")
        return False
    doc = out["didDocument"]
    resolved = json.loads(doc) if isinstance(doc, str) else doc
    vid = resolved.get("versionId")
    if vid != expected_version_id:
        logger.error("Result: FAIL — expected versionId %s after deactivate, got %s", expected_version_id, vid)
        return False
    if resolved.get("updateRules") != {}:
        logger.error("Result: FAIL — deactivated doc must have updateRules {}; got %s", resolved.get("updateRules"))
        return False
    empty_list_fields = (
        "verificationMethod",
        "authentication",
        "assertionMethod",
        "keyAgreement",
        "capabilityInvocation",
        "capabilityDelegation",
    )
    for field in empty_list_fields:
        val = resolved.get(field)
        if val is not None and val != []:
            logger.error("Result: FAIL — deactivated doc must have %s []; got %s", field, val)
            return False
    logger.info(
        "Result: PASS — %s resolver returned deactivated document (versionId=%s, updateRules={}, all key arrays [])",
        resolver_name,
        expected_version_id,
    )
    return True


def _run_both_reference_resolvers_and_assert_deactivated(
    did: str,
    vdg_url: str | None,
    expected_version_id: int = 2,
) -> bool:
    """Run Python then Rust resolver; both must assert deactivated document shape.

    Used by scenarios 21–22 (TS controller) for cross-implementation read checks.
    """
    if not _run_resolve_and_assert_deactivated(did, "python", vdg_url, expected_version_id):
        return False
    if not _run_resolve_and_assert_deactivated(did, "rust", vdg_url, expected_version_id):
        return False
    return True


def run_scenario(
    controller_kind: str,
    vdr_kind: str,
    resolver_kind: str,
    use_vdg: bool,
    wallet_dir: Path,
) -> bool:
    """Execute one interop scenario.

    Reference-controller scenarios (1–20): create → resolve (v0) → update →
    resolve (v1) → deactivate → resolve (v2, tombstone checks).

    TS-controller scenarios (21–22): create → both reference resolvers (v0) →
    update → both reference resolvers (v1) → deactivate → both reference
    resolvers (v2, tombstone checks).
    """
    if controller_kind == "zkred":
        return _run_ts_controller_scenario(vdr_kind, wallet_dir)

    vdr_url = RUST_VDR_URL if vdr_kind == "rust" else PYTHON_VDR_URL
    vdr_create_endpoint = vdr_url
    vdg_url = VDG_URL if use_vdg else None

    try:
        # 1. Create
        if controller_kind == "python":
            did = _run_python_controller_create(vdr_create_endpoint, wallet_dir)
        else:
            did = _run_rust_controller_create(vdr_create_endpoint, wallet_dir)
        base_did = did.split("?")[0] if "?" in did else did

        # 2. Resolve after create (versionId=0)
        if vdg_url:
            time.sleep(0.3)
        logger.info("Action: Resolve after create — expect versionId=0")
        ok, root_self_hash = _run_resolve_and_assert(base_did, resolver_kind, vdg_url, 0)
        if not ok:
            return False
        if vdg_url and root_self_hash:
            if not _assert_vdg_headers(vdg_url, base_did, root_self_hash, expected_cache_hit=False, use_version_id_param=False):
                return False
            did_v0 = f"{base_did}?versionId=0"
            if not _assert_vdg_headers(vdg_url, did_v0, root_self_hash, expected_cache_hit=True, use_version_id_param=True):
                return False

        # 3. Update
        if controller_kind == "python":
            _run_python_controller_update(base_did, wallet_dir)
        else:
            _run_rust_controller_update(wallet_dir, base_did)

        # 4. Verify VDR GET
        path = _resolution_path(base_did)
        url = f"{vdr_url.rstrip('/')}/{path}"
        logger.info("Action: GET from VDR — fetch did-documents.jsonl")
        r = httpx.get(url, timeout=10.0)
        if r.status_code != 200:
            logger.error("Result: FAIL — GET returned %s", r.status_code)
            return False
        # Response should contain at least two lines (root + update); update has versionId 1
        lines = [ln.strip() for ln in r.text.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            logger.error("Result: FAIL — VDR response has %s lines, expected at least 2", len(lines))
            return False
        last_doc = json.loads(lines[-1])
        if last_doc.get("versionId") != 1:
            logger.error("Result: FAIL — latest doc versionId=%s", last_doc.get("versionId"))
            return False
        update_self_hash = last_doc.get("selfHash")
        logger.info("Result: PASS — VDR returns latest (versionId=1)")

        if vdg_url:
            time.sleep(0.5)

        # 5. Resolve after update (versionId=1)
        logger.info("Action: Resolve after update — expect versionId=1")
        ok, _ = _run_resolve_and_assert(base_did, resolver_kind, vdg_url, 1)
        if not ok:
            return False
        if vdg_url and update_self_hash:
            if not _assert_vdg_headers(vdg_url, base_did, update_self_hash, expected_cache_hit=False, use_version_id_param=False):
                return False
            did_with_version = f"{base_did}?versionId=1"
            if not _assert_vdg_headers(vdg_url, did_with_version, update_self_hash, expected_cache_hit=True, use_version_id_param=True):
                return False

        # 6. Deactivate
        if controller_kind == "python":
            _run_python_controller_deactivate(base_did, wallet_dir)
        else:
            _run_rust_controller_deactivate(wallet_dir, base_did)

        if vdg_url:
            time.sleep(0.5)

        # 7. Resolve after deactivate (versionId=2, updateRules {}, all key arrays [])
        logger.info("Action: Resolve after deactivate — expect versionId=2, updateRules={}, key arrays []")
        if not _run_resolve_and_assert_deactivated(base_did, resolver_kind, vdg_url, expected_version_id=2):
            return False

        return True
    except RuntimeError as e:
        logger.error("Result: FAIL — %s", e)
        return False


def _run_ts_controller_scenario(vdr_kind: str, wallet_dir: Path) -> bool:
    """Scenarios 21–22: TS create/update/deactivate; both Python and Rust resolvers verify."""
    vdr_url = RUST_VDR_URL if vdr_kind == "rust" else PYTHON_VDR_URL
    vdg_url = None  # VDG omitted for TS controller scenarios

    try:
        # 1. Create via TS controller
        did = _run_zkred_controller_create(vdr_url, wallet_dir)
        base_did = did.split("?")[0] if "?" in did else did

        # 2. Both reference resolvers after create (versionId=0)
        logger.info("Action: Resolve after create (Python and Rust) — expect versionId=0")
        ok, _ = _run_both_reference_resolvers_and_assert(base_did, vdg_url, 0)
        if not ok:
            return False

        # 3. Update via TS controller
        _run_zkred_controller_update(base_did, wallet_dir)

        # 4. Verify VDR GET
        path = _resolution_path(base_did)
        url = f"{vdr_url.rstrip('/')}/{path}"
        logger.info("Action: GET from VDR — fetch did-documents.jsonl")
        r = httpx.get(url, timeout=10.0)
        if r.status_code != 200:
            logger.error("Result: FAIL — GET returned %s", r.status_code)
            return False
        lines = [ln.strip() for ln in r.text.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            logger.error("Result: FAIL — VDR response has %s lines, expected at least 2", len(lines))
            return False
        last_doc = json.loads(lines[-1])
        if last_doc.get("versionId") != 1:
            logger.error("Result: FAIL — latest doc versionId=%s", last_doc.get("versionId"))
            return False
        logger.info("Result: PASS — VDR returns latest (versionId=1)")

        # 5. Both reference resolvers after update (versionId=1)
        logger.info("Action: Resolve after update (Python and Rust) — expect versionId=1")
        ok, _ = _run_both_reference_resolvers_and_assert(base_did, vdg_url, 1)
        if not ok:
            return False

        # 6. Deactivate via TS controller
        _run_zkred_controller_deactivate(base_did, wallet_dir)

        # 7. Both reference resolvers after deactivate (versionId=2, tombstone shape)
        logger.info(
            "Action: Resolve after deactivate (Python and Rust) — "
            "expect versionId=2, updateRules={}, key arrays []"
        )
        if not _run_both_reference_resolvers_and_assert_deactivated(
            base_did, vdg_url, expected_version_id=2
        ):
            return False

        return True
    except RuntimeError as e:
        logger.error("Result: FAIL — %s", e)
        return False


def _zkred_pinned_version() -> str:
    """Return the lockfile-pinned @zkred/did-webplus version, or a fallback string."""
    try:
        data = json.loads(PACKAGE_LOCK_PATH.read_text(encoding="utf-8"))
        version = data.get("packages", {}).get(ZKRED_LOCKFILE_KEY, {}).get("version")
        if version:
            return str(version)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return "unknown"


def _controller_display_name(controller_kind: str) -> str:
    """Human-readable controller name for logs."""
    return {"python": "Python", "rust": "Rust", "zkred": "Zkred/TS"}.get(
        controller_kind, controller_kind.capitalize()
    )


def _log_summary(n: int, controller: str, vdr: str, resolver: str, use_vdg: bool) -> None:
    """Parameterized summary for scenario n."""
    vdg_str = "Rust VDG" if use_vdg else "no VDG"
    logger.info(
        "Summary — Scenario %s: %s controller, %s VDR, %s resolver, %s",
        n,
        _controller_display_name(controller),
        vdr.capitalize(),
        _resolver_display_name(resolver),
        vdg_str,
    )
    if controller == "zkred" or resolver == "both":
        logger.info(
            "  TS controller created, updated, and deactivated DID; Python and Rust "
            "resolvers verified after create (v0), update (v1), and deactivate (v2)."
        )
    else:
        logger.info(
            "  Controller created, updated, and deactivated DID; resolver ran after create (v0), update (v1), and deactivate (v2)."
        )


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ./run_interop_tests.py <1-22>")
        print("Scenarios 1-16: Controller/VDR/Resolver (Python/Rust) × VDG (no/yes).")
        print("Scenarios 17-20: Zkred/TS resolver with reference controller + VDR full lifecycle.")
        print("Scenarios 21-22: Zkred/TS controller full lifecycle; Python and Rust resolvers verify.")
        return 1
    scenario_arg = sys.argv[1]
    try:
        n = int(scenario_arg)
    except ValueError:
        n = -1
    if n < 1 or n > 22:
        print("Scenario must be 1-22")
        return 1

    controller_kind, vdr_kind, resolver_kind, use_vdg = _scenario_params(n)
    logger.info(
        "=== Scenario %s: %s controller, %s VDR, %s resolver, %s ===",
        n,
        _controller_display_name(controller_kind),
        vdr_kind.capitalize(),
        _resolver_display_name(resolver_kind),
        "Rust VDG" if use_vdg else "no VDG",
    )
    if 17 <= n <= 22:
        logger.info(
            "=== TS interop: @zkred/did-webplus %s (from package-lock.json) ===",
            _zkred_pinned_version(),
        )
        logger.info(
            "=== Version management: see interop/README.md or interop/ZKRED_VERSION.md ==="
        )

    logger.info("Waiting for services...")
    time.sleep(3)

    wallet_dir = INTEROP_DIR / f"wallet_dir_scenario_{n}"
    if wallet_dir.exists():
        shutil.rmtree(wallet_dir)
    wallet_dir.mkdir(parents=True, exist_ok=True)

    ok = run_scenario(controller_kind, vdr_kind, resolver_kind, use_vdg, wallet_dir)
    if ok:
        logger.info("=== All tests PASSED ===")
        _log_summary(n, controller_kind, vdr_kind, resolver_kind, use_vdg)
    else:
        logger.error("=== Tests FAILED ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
