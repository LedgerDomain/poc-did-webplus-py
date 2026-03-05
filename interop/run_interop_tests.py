#!/usr/bin/env python3
"""
Run interoperability tests for did:webplus.

16 scenarios from 4 binary axes: Controller (Python/Rust), VDR (Python/Rust),
Resolver (Python/Rust), VDG (no/yes). Create and update are performed by the
chosen controller CLI; resolution is performed by the chosen resolver.

Usage: ./run_interop_tests.py <1-16>
Or: docker compose up -d (with appropriate env) then ./run_interop_tests.py <1-16>
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

RUST_CLI_IMAGE = "ghcr.io/ledgerdomain/did-webplus-cli:v0.1.0"

# VDR base URLs and create endpoints
RUST_VDR_URL = "http://rust-vdr:8085"
PYTHON_VDR_URL = "http://python-vdr:8087"
VDG_URL = "http://rust-vdg:8086"

logger = logging.getLogger("interop")

# Enable DEBUG logging for interop tests (main process and resolver subprocess)
os.environ.setdefault("DID_WEBPLUS_LOG_LEVEL", "DEBUG")
# Use http for test hostnames (rust-vdr, rust-vdg, python-vdr)
HTTP_SCHEME_OVERRIDE = "rust-vdr=http,rust-vdg=http,python-vdr=http"
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


def _resolution_path(did: str) -> str:
    """Extract path for resolution URL from DID (path only; host/port are in the URL authority)."""
    components = parse_did(did)
    overrides = parse_http_scheme_overrides(
        os.environ.get("DID_WEBPLUS_HTTP_SCHEME_OVERRIDE")
    )
    full_url = components.resolution_url(http_scheme_overrides=overrides or None)
    parsed = urlparse(full_url)
    return parsed.path.lstrip("/") if parsed.path else ""


def _run_python_resolve(did: str, vdg_url: str | None = None) -> subprocess.CompletedProcess:
    """Run Python resolver. vdg_url: if set, resolve via VDG instead of VDR."""
    cmd = ["uv", "run", "did-webplus", "resolve", did, "-o", "json"]
    if vdg_url:
        cmd.extend(["--vdg-url", vdg_url.rstrip("/")])
    via = f" via VDG {vdg_url}" if vdg_url else " (direct from VDR)"
    logger.info("Running Python DID resolver%s", via)
    logger.info("Command: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=None,  # Let resolver logs (stderr) print to terminal
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        timeout=15,
    )


def _run_rust_resolve(did: str, vdg_url: str | None = None) -> subprocess.CompletedProcess:
    """Run Rust resolver via Docker. vdg_url: if set, resolve via VDG instead of VDR."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-e",
        f"DID_WEBPLUS_HTTP_SCHEME_OVERRIDE={HTTP_SCHEME_OVERRIDE}",
        "-e",
        "RUST_LOG=debug",
        RUST_CLI_IMAGE,
        "did",
        "resolve",
        did,
        "--json",
    ]
    if vdg_url:
        parsed = urlparse(vdg_url.rstrip("/"))
        vdg_host = parsed.netloc or parsed.path
        cmd.extend(["--vdg", vdg_host])
    via = f" via VDG {vdg_url}" if vdg_url else " (direct from VDR)"
    logger.info("Running Rust DID resolver%s", via)
    logger.info("Command: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=None,  # Let resolver logs (stderr) print to terminal
        text=True,
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


def _scenario_params(n: int) -> tuple[str, str, str, bool]:
    """Map scenario number 1-16 to (controller_kind, vdr_kind, resolver_kind, use_vdg)."""
    n0 = n - 1
    controller = "rust" if (n0 & 8) else "python"
    vdr = "rust" if (n0 & 4) else "python"
    resolver = "rust" if (n0 & 2) else "python"
    use_vdg = bool(n0 & 1)
    return controller, vdr, resolver, use_vdg


def _run_resolve_and_assert(
    did: str,
    resolver_kind: str,
    vdg_url: str | None,
    expected_version_id: int,
) -> tuple[bool, str | None]:
    """Run chosen resolver, assert versionId. Returns (ok, resolved_self_hash or None)."""
    if resolver_kind == "python":
        result = _run_python_resolve(did, vdg_url=vdg_url)
    else:
        result = _run_rust_resolve(did, vdg_url=vdg_url)
    resolver_name = "Python" if resolver_kind == "python" else "Rust"
    if result.returncode != 0:
        logger.error("Result: FAIL — %s resolve failed: %s", resolver_name, result.stderr or "(see stderr)")
        return False, None
    out = json.loads(result.stdout)
    if not out.get("didDocument"):
        logger.error("Result: FAIL — no didDocument in result")
        return False, None
    resolved = json.loads(out["didDocument"])
    vid = resolved.get("versionId")
    if vid != expected_version_id:
        logger.error("Result: FAIL — expected versionId %s, got %s", expected_version_id, vid)
        return False, None
    logger.info("Result: PASS — %s resolver returned versionId=%s", resolver_name, expected_version_id)
    return True, resolved.get("selfHash")


def run_scenario(
    controller_kind: str,
    vdr_kind: str,
    resolver_kind: str,
    use_vdg: bool,
    wallet_dir: Path,
) -> bool:
    """Execute one interop scenario: controller create -> resolve (v0) -> update -> verify VDR -> resolve (v1) [+ VDG checks]."""
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

        return True
    except RuntimeError as e:
        logger.error("Result: FAIL — %s", e)
        return False


def _log_summary(n: int, controller: str, vdr: str, resolver: str, use_vdg: bool) -> None:
    """Parameterized summary for scenario n."""
    vdg_str = "Rust VDG" if use_vdg else "no VDG"
    logger.info(
        "Summary — Scenario %s: %s controller, %s VDR, %s resolver, %s",
        n, controller.capitalize(), vdr.capitalize(), resolver.capitalize(), vdg_str,
    )
    logger.info(
        "  Controller created and updated DID; resolver ran after create (versionId=0) and after update (versionId=1)."
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ./run_interop_tests.py <1-16>")
        print("Scenarios: 4 axes — Controller (Python/Rust), VDR (Python/Rust), Resolver (Python/Rust), VDG (no/yes).")
        return 1
    scenario_arg = sys.argv[1]
    try:
        n = int(scenario_arg)
    except ValueError:
        n = -1
    if n < 1 or n > 16:
        print("Scenario must be 1-16")
        return 1

    controller_kind, vdr_kind, resolver_kind, use_vdg = _scenario_params(n)
    logger.info(
        "=== Scenario %s: %s controller, %s VDR, %s resolver, %s ===",
        n,
        controller_kind.capitalize(),
        vdr_kind.capitalize(),
        resolver_kind.capitalize(),
        "Rust VDG" if use_vdg else "no VDG",
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
