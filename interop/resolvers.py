"""Shared did:webplus resolver invocations for interop runners."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

INTEROP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = str(INTEROP_DIR.parent)

RUST_CLI_IMAGE = "ghcr.io/ledgerdomain/did-webplus-cli:v0.1.5"
# Third-party Zkred TS runner image (not a poc-* tag).
ZKRED_IMAGE = "did-webplus-zkred"

# Use http for test hostnames (rust-vdr, rust-vdg, python-vdr, ledgerdomain.github.io)
HTTP_SCHEME_OVERRIDE = (
    "rust-vdr=http,rust-vdg=http,python-vdr=http,ledgerdomain.github.io=http"
)

logger = logging.getLogger("interop")


def _run_python_resolve(
    did: str,
    vdg_url: str | None = None,
    *,
    base_dir: Path | str | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess:
    """Run Python resolver. vdg_url: if set, resolve via VDG instead of VDR."""
    cmd = ["uv", "run", "did-webplus", "resolve", did, "-o", "json"]
    if base_dir is not None:
        cmd.extend(["--base-dir", str(base_dir)])
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
        cwd=_REPO_ROOT,
        timeout=timeout,
    )


def _run_rust_resolve(
    did: str,
    vdg_url: str | None = None,
    *,
    base_dir: Path | str | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess:
    """Run Rust resolver via Docker. vdg_url: if set, resolve via VDG instead of VDR.

    ``base_dir`` is accepted for API parity with the Python helper; the Rust CLI
    resolve path does not use a wallet/base-dir mount.
    """
    del base_dir  # unused; kept for shared caller signature
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
        timeout=timeout,
    )


def _run_zkred_resolve(
    did: str,
    vdg_url: str | None = None,
    *,
    base_dir: Path | str | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess:
    """Run Zkred/TS resolver via Docker (or local node if INTEROP_ZKRED_LOCAL is set).

    Image entrypoint is ``node ts_runner.mjs``; args are resolve <did> [-o json]
    and optional --vdg-url. Uses --network host so rust-vdr / python-vdr / rust-vdg
    resolve via /etc/hosts, same as the Rust CLI helper.

    ``base_dir`` is accepted for API parity with the Python helper; the Zkred
    resolve path does not use a wallet/base-dir.
    """
    del base_dir  # unused; kept for shared caller signature
    resolve_args = ["resolve", did, "-o", "json"]
    if vdg_url:
        resolve_args.extend(["--vdg-url", vdg_url.rstrip("/")])
    via = f" via VDG {vdg_url}" if vdg_url else " (direct from VDR)"
    if os.environ.get("INTEROP_ZKRED_LOCAL"):
        cmd = ["node", str(INTEROP_DIR / "ts_runner.mjs"), *resolve_args]
        cwd: str | None = str(INTEROP_DIR)
    else:
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            ZKRED_IMAGE,
            *resolve_args,
        ]
        cwd = None
    logger.info("Running Zkred/TS DID resolver%s", via)
    logger.info("Command: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=None,  # Let resolver logs (stderr) print to terminal
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
