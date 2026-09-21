"""Shared did:webplus resolver adapter layer for interop runners."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

INTEROP_DIR = Path(__file__).resolve().parent

RUST_CLI_IMAGE = "ghcr.io/ledgerdomain/did-webplus-cli:v0.1.6"
PYTHON_CLI_IMAGE = "did-webplus-python-cli"
# Third-party Zkred TS runner image (not a poc-* tag).
ZKRED_IMAGE = "did-webplus-zkred"

# Sibling docker run network; default "host" for host-based /etc/hosts runs.
DOCKER_NETWORK = os.environ.get("DID_WEBPLUS_INTEROP_DOCKER_NETWORK", "host")

# Use http for test hostnames (rust-vdr, rust-vdg, python-vdr, ledgerdomain.github.io)
HTTP_SCHEME_OVERRIDE = (
    "rust-vdr=http,rust-vdg=http,python-vdr=http,ledgerdomain.github.io=http"
)

ResolverKind = Literal["python", "rust", "zkred"]

logger = logging.getLogger("interop")

# ---------------------------------------------------------------------------
# Pinned Rust CLI `did resolve --help` (ghcr.io/ledgerdomain/did-webplus-cli:v0.1.6)
# ---------------------------------------------------------------------------
# Options mapping for resolution wire options:
#   requestCreate        -> -C, --creation
#   requestNext          -> -N, --next
#   requestLatest        -> -L, --latest
#   requestDeactivated   -> -D, --deactivated
#   localResolutionOnly  -> -l, --local-resolution-only
# Store for full resolver: --did-doc-store sqlite://<path> (env DID_WEBPLUS_DID_DOC_STORE)
# JSON output: -j, --json
# VDG (thin/full): --vdg <HOST>
# HTTP scheme override: --http-scheme-override (env DID_WEBPLUS_HTTP_SCHEME_OVERRIDE)
# ---------------------------------------------------------------------------

RUST_DOC_STORE_CONTAINER_PATH = "/data/did-doc-store.db"
RUST_DOC_STORE_URL = f"sqlite://{RUST_DOC_STORE_CONTAINER_PATH}?mode=rwc"

PYTHON_OPTION_SUPPORT: dict[str, bool] = {
    "requestCreate": False,
    "requestNext": False,
    "requestLatest": False,
    "requestDeactivated": False,
    "localResolutionOnly": True,  # --no-fetch
}

RUST_OPTION_SUPPORT: dict[str, bool] = {
    "requestCreate": True,
    "requestNext": True,
    "requestLatest": True,
    "requestDeactivated": True,
    "localResolutionOnly": True,
}

ZKRED_OPTION_SUPPORT: dict[str, bool] = {
    "requestCreate": False,
    "requestNext": False,
    "requestLatest": False,
    "requestDeactivated": False,
    "localResolutionOnly": False,
}


@dataclass(frozen=True)
class ResolutionOptions:
    """Wire-format resolution options (did-webplus-resolution-scenario / resolver API)."""

    request_create: bool = False
    request_next: bool = False
    request_latest: bool = False
    request_deactivated: bool = False
    local_resolution_only: bool = False

    @classmethod
    def from_wire(cls, wire: dict[str, Any] | None) -> ResolutionOptions:
        if not wire:
            return cls()
        return cls(
            request_create=bool(wire.get("requestCreate")),
            request_next=bool(wire.get("requestNext")),
            request_latest=bool(wire.get("requestLatest")),
            request_deactivated=bool(wire.get("requestDeactivated")),
            local_resolution_only=bool(wire.get("localResolutionOnly")),
        )

    def active_wire_names(self) -> tuple[str, ...]:
        """Wire keys that are true in this options object."""
        out: list[str] = []
        if self.request_create:
            out.append("requestCreate")
        if self.request_next:
            out.append("requestNext")
        if self.request_latest:
            out.append("requestLatest")
        if self.request_deactivated:
            out.append("requestDeactivated")
        if self.local_resolution_only:
            out.append("localResolutionOnly")
        return tuple(out)


@dataclass
class ResolveResult:
    """Full DID resolution result after CLI invocation and stdout parsing."""

    did_document: dict[str, Any] | None
    did_document_metadata: dict[str, Any] | None
    did_resolution_metadata: dict[str, Any] | None
    returncode: int
    stdout: str
    stderr: str
    unsupported_options: tuple[str, ...] = ()
    parse_error: str | None = None
    resolver: ResolverKind | None = None

    def as_completed_process(self) -> subprocess.CompletedProcess[str]:
        """Legacy shape for matrix runner until matrix-migration todo."""
        return subprocess.CompletedProcess(
            args=[],
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _unsupported_for(
    options: ResolutionOptions,
    support_m: dict[str, bool],
) -> tuple[str, ...]:
    unsupported: list[str] = []
    for name in options.active_wire_names():
        if not support_m.get(name, False):
            unsupported.append(name)
    return tuple(unsupported)


def parse_resolve_stdout(stdout: str) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    str | None,
]:
    """
    Parse resolver JSON stdout into (didDocument dict, didDocumentMetadata, didResolutionMetadata, error).
    didDocument may be a JCS string or object in the wire JSON.
    """
    if not stdout.strip():
        return None, None, None, "empty stdout"
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError as e:
        return None, None, None, f"invalid JSON stdout: {e}"
    if not isinstance(out, dict):
        return None, None, None, "stdout JSON is not an object"

    doc_raw = out.get("didDocument")
    doc: dict[str, Any] | None = None
    if doc_raw is not None:
        if isinstance(doc_raw, str):
            if doc_raw:
                try:
                    parsed = json.loads(doc_raw)
                except json.JSONDecodeError as e:
                    return None, None, None, f"didDocument string is not JSON: {e}"
                doc = parsed if isinstance(parsed, dict) else None
            else:
                doc = None
        elif isinstance(doc_raw, dict):
            doc = doc_raw
        else:
            return None, None, None, "didDocument has unexpected type"

    meta = out.get("didDocumentMetadata")
    doc_meta = meta if isinstance(meta, dict) else None
    res_meta_raw = out.get("didResolutionMetadata")
    res_meta = res_meta_raw if isinstance(res_meta_raw, dict) else None
    return doc, doc_meta, res_meta, None


def _parse_rust_cli_stderr(stderr: str) -> dict[str, Any] | None:
    """
    Rust CLI often prints resolution failures on stderr (non-zero exit, empty stdout).

    Parses the Debug ``DIDResolutionMetadata { ... }`` line or a plain ``Error:`` message.
    """
    text = stderr.strip()
    if not text:
        return None

    if "DIDResolutionMetadata {" in text:
        meta: dict[str, Any] = {}
        ct_m = re.search(r'content_type: "([^"]*)"', text)
        if ct_m:
            meta["contentType"] = ct_m.group(1)
        err_m = re.search(r'error_o: Some\("((?:\\.|[^"\\])*)"\)', text)
        if err_m:
            meta["error"] = err_m.group(1).replace('\\"', '"').replace("\\\\", "\\")
        for rust_key, wire_key in (
            ("fetched_updates_from_vdr", "fetchedUpdatesFromVDR"),
            ("did_document_resolved_locally", "didDocumentResolvedLocally"),
            (
                "did_document_metadata_resolved_locally",
                "didDocumentMetadataResolvedLocally",
            ),
        ):
            bm = re.search(rf"{re.escape(rust_key)}: (true|false)", text)
            if bm:
                meta[wire_key] = bm.group(1) == "true"
        if meta:
            return meta

    err_m = re.search(r"^Error:\s*(.+)$", text, re.MULTILINE)
    if err_m:
        msg = err_m.group(1).strip()
        if "DIDResolutionMetadata {" in msg:
            nested = _parse_rust_cli_stderr(msg)
            if nested:
                return nested
        return {"contentType": "application/did+json", "error": msg}
    return None


def _completed_to_result(
    proc: subprocess.CompletedProcess[str],
    *,
    resolver: ResolverKind,
    unsupported_options: tuple[str, ...],
) -> ResolveResult:
    doc, doc_meta, res_meta, parse_error = parse_resolve_stdout(proc.stdout)
    if resolver == "rust":
        stderr_meta = _parse_rust_cli_stderr(proc.stderr)
        if stderr_meta:
            merged = dict(res_meta or {})
            merged.update(stderr_meta)
            res_meta = merged
            if parse_error == "empty stdout" and res_meta.get("error"):
                parse_error = None
    return ResolveResult(
        did_document=doc,
        did_document_metadata=doc_meta,
        did_resolution_metadata=res_meta,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr or "",
        unsupported_options=unsupported_options,
        parse_error=parse_error,
        resolver=resolver,
    )


def _store_mount_path(store_dir: Path | str) -> Path:
    path = Path(store_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_python_cmd(
    did_query: str,
    store_host_path: Path,
    options: ResolutionOptions,
    vdg_url: str | None,
) -> list[str]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        DOCKER_NETWORK,
        "-v",
        f"{store_host_path}:/data",
        "-e",
        f"DID_WEBPLUS_HTTP_SCHEME_OVERRIDE={HTTP_SCHEME_OVERRIDE}",
        PYTHON_CLI_IMAGE,
        "resolve",
        did_query,
        "-o",
        "json",
    ]
    if options.local_resolution_only:
        cmd.append("--no-fetch")
    if vdg_url:
        cmd.extend(["--vdg-url", vdg_url.rstrip("/")])
    return cmd


def _build_rust_cmd(
    did_query: str,
    store_host_path: Path,
    options: ResolutionOptions,
    vdg_url: str | None,
) -> list[str]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        DOCKER_NETWORK,
        "-v",
        f"{store_host_path}:/data",
        "-e",
        f"DID_WEBPLUS_HTTP_SCHEME_OVERRIDE={HTTP_SCHEME_OVERRIDE}",
        "-e",
        "RUST_LOG=debug",
        RUST_CLI_IMAGE,
        "did",
        "resolve",
        did_query,
        "--json",
        "--did-doc-store",
        RUST_DOC_STORE_URL,
    ]
    if options.request_create:
        cmd.append("--creation")
    if options.request_next:
        cmd.append("--next")
    if options.request_latest:
        cmd.append("--latest")
    if options.request_deactivated:
        cmd.append("--deactivated")
    if options.local_resolution_only:
        cmd.append("--local-resolution-only")
    if vdg_url:
        parsed = urlparse(vdg_url.rstrip("/"))
        vdg_host = parsed.netloc or parsed.path
        cmd.extend(["--vdg", vdg_host])
    return cmd


def _build_zkred_cmd(
    did_query: str,
    store_host_path: Path,
    vdg_url: str | None,
) -> list[str]:
    resolve_args = ["resolve", did_query, "-o", "json"]
    if vdg_url:
        resolve_args.extend(["--vdg-url", vdg_url.rstrip("/")])
    if os.environ.get("INTEROP_ZKRED_LOCAL"):
        return ["node", str(INTEROP_DIR / "ts_runner.mjs"), *resolve_args]
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        DOCKER_NETWORK,
        "-v",
        f"{store_host_path}:/wallet",
        ZKRED_IMAGE,
        *resolve_args,
    ]


def resolve(
    resolver: ResolverKind,
    did_query: str,
    *,
    options: ResolutionOptions | None = None,
    store_dir: Path | str,
    vdg_url: str | None = None,
    timeout: float = 15,
) -> ResolveResult:
    """
    Resolve ``did_query`` via the chosen implementation adapter.

    ``store_dir`` is a host directory mounted into the resolver container for
    persistent per-scenario DID doc storage (Python ``/data``, Rust ``/data``,
    Zkred ``/wallet`` — Zkred does not persist resolve state across runs today).
    """
    opts = options or ResolutionOptions()
    store_path = _store_mount_path(store_dir)

    if resolver == "python":
        unsupported = _unsupported_for(opts, PYTHON_OPTION_SUPPORT)
        cmd = _build_python_cmd(did_query, store_path, opts, vdg_url)
        cwd: str | None = None
    elif resolver == "rust":
        unsupported = _unsupported_for(opts, RUST_OPTION_SUPPORT)
        cmd = _build_rust_cmd(did_query, store_path, opts, vdg_url)
        cwd = None
    elif resolver == "zkred":
        unsupported = _unsupported_for(opts, ZKRED_OPTION_SUPPORT)
        cmd = _build_zkred_cmd(did_query, store_path, vdg_url)
        cwd = str(INTEROP_DIR) if os.environ.get("INTEROP_ZKRED_LOCAL") else None
    else:
        raise ValueError(f"unknown resolver {resolver!r}")

    via = f" via VDG {vdg_url}" if vdg_url else " (direct from VDR)"
    logger.info("Running %s DID resolver%s", resolver, via)
    if unsupported:
        logger.info(
            "Unsupported resolution options for %s (not sent to CLI): %s",
            resolver,
            ", ".join(unsupported),
        )
    logger.info("Command: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return ResolveResult(
            did_document=None,
            did_document_metadata=None,
            did_resolution_metadata=None,
            returncode=-1,
            stdout=e.stdout or "" if e.stdout else "",
            stderr=e.stderr or "" if e.stderr else "",
            unsupported_options=unsupported,
            parse_error=f"timeout after {timeout}s",
            resolver=resolver,
        )

    return _completed_to_result(
        proc, resolver=resolver, unsupported_options=unsupported
    )


def _run_python_resolve(
    did: str,
    vdg_url: str | None = None,
    *,
    base_dir: Path | str | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess[str]:
    """Run Python resolver (docker CLI). Legacy wrapper for matrix runner."""
    if base_dir is not None:
        store = Path(base_dir)
        result = resolve(
            "python",
            did,
            store_dir=store,
            vdg_url=vdg_url,
            timeout=timeout,
        )
        return result.as_completed_process()
    with tempfile.TemporaryDirectory(prefix="interop-py-store-") as tmp:
        result = resolve(
            "python",
            did,
            store_dir=tmp,
            vdg_url=vdg_url,
            timeout=timeout,
        )
        return result.as_completed_process()


def _run_rust_resolve(
    did: str,
    vdg_url: str | None = None,
    *,
    base_dir: Path | str | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess[str]:
    """Run Rust resolver via Docker. Legacy wrapper for matrix runner."""
    store = Path(base_dir) if base_dir is not None else None
    if store is None:
        with tempfile.TemporaryDirectory(prefix="interop-rust-store-") as tmp:
            result = resolve(
                "rust",
                did,
                store_dir=tmp,
                vdg_url=vdg_url,
                timeout=timeout,
            )
            return result.as_completed_process()
    result = resolve(
        "rust",
        did,
        store_dir=store,
        vdg_url=vdg_url,
        timeout=timeout,
    )
    return result.as_completed_process()


def _run_zkred_resolve(
    did: str,
    vdg_url: str | None = None,
    *,
    base_dir: Path | str | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess[str]:
    """Run Zkred/TS resolver via Docker. Legacy wrapper for matrix runner."""
    store = Path(base_dir) if base_dir is not None else None
    if store is None:
        with tempfile.TemporaryDirectory(prefix="interop-zkred-store-") as tmp:
            result = resolve(
                "zkred",
                did,
                store_dir=tmp,
                vdg_url=vdg_url,
                timeout=timeout,
            )
            return result.as_completed_process()
    result = resolve(
        "zkred",
        did,
        store_dir=store,
        vdg_url=vdg_url,
        timeout=timeout,
    )
    return result.as_completed_process()
