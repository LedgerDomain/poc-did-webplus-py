"""CLI for did:webplus DID resolution and VDR service."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from did_webplus.controller import ControllerError, create_did, deactivate_did, update_did
from did_webplus.did import parse_http_scheme_overrides
from did_webplus.logging_config import configure_logging
from did_webplus.resolution import ResolutionOptions
from did_webplus.resolver import FullDIDResolver
from did_webplus.store import SQLiteDIDDocStore
from did_webplus.vdr import VDRConfig, create_vdr_app

app = typer.Typer(
    name="did-webplus",
    help="Resolve did:webplus DIDs and run VDR service",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """Configure logging from env before any command runs."""
    if ctx.invoked_subcommand is not None:
        configure_logging()


def _default_base_dir() -> Path:
    """Default base directory: ~/.poc-did-webplus-py (store, controller keys)."""
    return Path.home() / ".poc-did-webplus-py"


def _parse_bool_env(val: str | None) -> bool:
    """Parse env var as boolean for flag options."""
    if val is None:
        return False
    return val.lower() in ("1", "true", "yes", "on")


def _coerce_bool_flag(val: bool | str | None) -> bool:
    """Normalize Typer/env bool flags (env may arrive as str)."""
    if isinstance(val, str):
        return _parse_bool_env(val)
    if val is None:
        return False
    return bool(val)


@app.command("resolve")
def resolve_cmd(
    did: str = typer.Argument(..., help="DID to resolve (e.g. did:webplus:example.com:...)"),
    base_dir: Path = typer.Option(
        default_factory=_default_base_dir,
        path_type=Path,
        envvar="DID_WEBPLUS_BASE_DIR",
        help="Base directory (did_documents.db, controller keys; or set DID_WEBPLUS_BASE_DIR)",
    ),
    vdg_url: str | None = typer.Option(
        default=None,
        envvar="DID_WEBPLUS_VDG_URL",
        help="VDG base URL for fetching (or set DID_WEBPLUS_VDG_URL)",
    ),
    output: str = typer.Option(
        "pretty",
        "--output",
        "-o",
        envvar="DID_WEBPLUS_OUTPUT",
        help="Output format: json or pretty (or set DID_WEBPLUS_OUTPUT)",
    ),
    request_create: bool = typer.Option(
        False,
        "--creation",
        help="Request creation (created / createdMilliseconds) metadata",
    ),
    request_next: bool = typer.Option(
        False,
        "--next",
        help="Request next-update metadata when a successor exists",
    ),
    request_latest: bool = typer.Option(
        False,
        "--latest",
        help="Request latest-update metadata",
    ),
    request_deactivated: bool = typer.Option(
        False,
        "--deactivated",
        help="Request deactivated metadata (emit false when not deactivated)",
    ),
    local_resolution_only: bool = typer.Option(
        False,
        "--local-resolution-only",
        help="Resolve only from local store; fail if a fetch would be required",
    ),
    no_fetch: bool = typer.Option(
        False,
        "--no-fetch",
        envvar="DID_WEBPLUS_NO_FETCH",
        help="Alias for --local-resolution-only (or set DID_WEBPLUS_NO_FETCH=1)",
    ),
    http_scheme_override: str | None = typer.Option(
        None,
        "--http-scheme-override",
        envvar="DID_WEBPLUS_HTTP_SCHEME_OVERRIDE",
        help="Comma-separated hostname=scheme pairs (e.g. rust-vdr=http,python-vdr=http). "
        "Overrides default: localhost uses http, others use https. Use http only for testing.",
    ),
) -> None:
    """Resolve a did:webplus DID and print the result."""
    request_create = _coerce_bool_flag(request_create)
    request_next = _coerce_bool_flag(request_next)
    request_latest = _coerce_bool_flag(request_latest)
    request_deactivated = _coerce_bool_flag(request_deactivated)
    local_resolution_only = _coerce_bool_flag(local_resolution_only)
    no_fetch = _coerce_bool_flag(no_fetch)

    base_path = base_dir.expanduser().resolve()
    store_path = base_path / "did_documents.db"
    store_path.parent.mkdir(parents=True, exist_ok=True)

    if output not in ("json", "pretty"):
        typer.echo(f"Invalid output format: {output}. Use 'json' or 'pretty'.", err=True)
        raise typer.Exit(2)

    store_impl = SQLiteDIDDocStore(store_path)
    http_scheme_overrides = parse_http_scheme_overrides(http_scheme_override)
    resolver = FullDIDResolver(
        store_impl,
        vdg_base_url=vdg_url,
        http_scheme_overrides=http_scheme_overrides or None,
    )

    options = ResolutionOptions.coalesce(
        ResolutionOptions(
            request_create=request_create,
            request_next=request_next,
            request_latest=request_latest,
            request_deactivated=request_deactivated,
            local_resolution_only=local_resolution_only,
        ),
        no_fetch=no_fetch,
    )
    result = resolver.resolve_or_result_sync(did, options=options)
    res_meta = result.did_resolution_metadata
    error = res_meta.get("error")

    if error:
        if output == "json":
            typer.echo(json.dumps(result.to_dict(), indent=2))
        else:
            if isinstance(error, dict):
                typer.echo(
                    f"{error.get('title', 'Error')}: {error.get('detail', error)}",
                    err=True,
                )
            else:
                typer.echo(str(error), err=True)
        raise typer.Exit(1)

    if output == "json":
        out = result.to_dict()
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo("=== DID Document (JCS) ===")
        typer.echo(result.did_document)
        typer.echo("\n=== DID Document Metadata ===")
        meta = result.did_document_metadata
        for key, value in meta.items():
            typer.echo(f"  {key}: {value}")
        typer.echo("\n=== DID Resolution Metadata ===")
        typer.echo(
            f"  fetchedUpdatesFromVDR: {res_meta.get('fetchedUpdatesFromVDR')}"
        )
        typer.echo(
            "  didDocumentResolvedLocally: "
            f"{res_meta.get('didDocumentResolvedLocally')}"
        )
        typer.echo(
            "  didDocumentMetadataResolvedLocally: "
            f"{res_meta.get('didDocumentMetadataResolvedLocally')}"
        )


@app.command("listen")
def listen_cmd(
    listen_port: int = typer.Option(
        80,
        "--listen-port",
        "-p",
        envvar="DID_WEBPLUS_VDR_LISTEN_PORT",
        help="Port to listen on; can be different than --did-port if e.g. dockerized or there is a reverse proxy (or set DID_WEBPLUS_VDR_LISTEN_PORT)",
    ),
    base_dir: Path = typer.Option(
        default_factory=_default_base_dir,
        path_type=Path,
        envvar="DID_WEBPLUS_BASE_DIR",
        help="Base directory (did_documents.db; or set DID_WEBPLUS_BASE_DIR)",
    ),
    did_hostname: str = typer.Option(
        ...,
        "--did-hostname",
        envvar="DID_WEBPLUS_VDR_DID_HOSTNAME",
        help="Hostname for DIDs hosted by this VDR (or set DID_WEBPLUS_VDR_DID_HOSTNAME)",
    ),
    did_port: int | None = typer.Option(
        None,
        "--did-port",
        envvar="DID_WEBPLUS_VDR_DID_PORT",
        help="Port number that will appear in DIDs hosted by this VDR (optional; or set DID_WEBPLUS_VDR_DID_PORT)",
    ),
    vdg_hosts: str = typer.Option(
        "",
        "--vdg-hosts",
        envvar="DID_WEBPLUS_VDR_VDG_HOSTS",
        help="Comma-separated VDG URLs to notify on updates (or set DID_WEBPLUS_VDR_VDG_HOSTS)",
    ),
    path_prefix: str | None = typer.Option(
        None,
        "--path-prefix",
        envvar="DID_WEBPLUS_VDR_PATH_PREFIX",
        help="Optional path prefix for DIDs (or set DID_WEBPLUS_VDR_PATH_PREFIX)",
    ),
) -> None:
    """Run the did:webplus VDR service in listen mode."""
    import uvicorn

    base_path = base_dir.expanduser().resolve()
    store_path = base_path / "did_documents.db"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_impl = SQLiteDIDDocStore(store_path)

    vdg_urls = [u.strip() for u in vdg_hosts.split(",") if u.strip()] if vdg_hosts else []

    config = VDRConfig(
        did_hostname=did_hostname,
        did_port=did_port,
        path_prefix=path_prefix,
        vdg_base_urls=vdg_urls,
        store=store_impl,
    )
    vdr_app = create_vdr_app(config)

    listen_hostname = "0.0.0.0"
    typer.echo(f"Starting VDR listening at http://{listen_hostname}:{listen_port}; listen_port={listen_port}, base_dir={base_dir}, did_hostname={did_hostname}, did_port={did_port}, vdg_hosts={vdg_hosts}, path_prefix={path_prefix}", err=True)
    uvicorn.run(vdr_app, host=listen_hostname, port=listen_port)


did_app = typer.Typer(help="DID controller operations")
app.add_typer(did_app, name="did")


@did_app.command("create")
def did_create_cmd(
    vdr_did_create_endpoint: str = typer.Argument(
        ...,
        help="VDR DID create endpoint URL (e.g. http://localhost:8085)",
    ),
    base_dir: Path = typer.Option(
        default_factory=_default_base_dir,
        path_type=Path,
        envvar="DID_WEBPLUS_BASE_DIR",
        help="Base directory (controller keys, did_documents.db; or set DID_WEBPLUS_BASE_DIR)",
    ),
    http_scheme_override: str | None = typer.Option(
        None,
        "--http-scheme-override",
        envvar="DID_WEBPLUS_HTTP_SCHEME_OVERRIDE",
        help="Comma-separated hostname=scheme pairs for resolution URL",
    ),
) -> None:
    """Create a new did:webplus DID and store the controller key."""
    base_path = base_dir.expanduser().resolve()
    http_scheme_overrides = parse_http_scheme_overrides(http_scheme_override)
    try:
        fully_qualified_did = create_did(
            vdr_did_create_endpoint,
            base_path,
            http_scheme_overrides=http_scheme_overrides or None,
        )
        typer.echo(fully_qualified_did)
    except ControllerError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


@did_app.command("update")
def did_update_cmd(
    did: str = typer.Argument(..., help="DID to update"),
    base_dir: Path = typer.Option(
        default_factory=_default_base_dir,
        path_type=Path,
        envvar="DID_WEBPLUS_BASE_DIR",
        help="Base directory (controller keys, did_documents.db; or set DID_WEBPLUS_BASE_DIR)",
    ),
    http_scheme_override: str | None = typer.Option(
        None,
        "--http-scheme-override",
        envvar="DID_WEBPLUS_HTTP_SCHEME_OVERRIDE",
        help="Comma-separated hostname=scheme pairs for resolution URL",
    ),
) -> None:
    """Update a did:webplus DID (key rotation)."""
    base_path = base_dir.expanduser().resolve()
    http_scheme_overrides = parse_http_scheme_overrides(http_scheme_override)
    try:
        fully_qualified_did = update_did(
            did,
            base_path,
            http_scheme_overrides=http_scheme_overrides or None,
        )
        typer.echo(fully_qualified_did)
    except ControllerError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


DEACTIVATE_CONFIRM_VALUE = "THIS-IS-IRREVERSIBLE"


@did_app.command("deactivate")
def did_deactivate_cmd(
    did: str = typer.Argument(..., help="DID to deactivate"),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help="Required confirmation: must be exactly THIS-IS-IRREVERSIBLE",
    ),
    base_dir: Path = typer.Option(
        default_factory=_default_base_dir,
        path_type=Path,
        envvar="DID_WEBPLUS_BASE_DIR",
        help="Base directory (controller keys, did_documents.db; or set DID_WEBPLUS_BASE_DIR)",
    ),
    http_scheme_override: str | None = typer.Option(
        None,
        "--http-scheme-override",
        envvar="DID_WEBPLUS_HTTP_SCHEME_OVERRIDE",
        help="Comma-separated hostname=scheme pairs for resolution URL",
    ),
) -> None:
    """Deactivate a did:webplus DID (tombstone)."""
    if confirm != DEACTIVATE_CONFIRM_VALUE:
        typer.echo(
            "DID deactivate is an irreversible action, and a confirmation is required.  The argument `--confirm THIS-IS-IRREVERSIBLE` is used to prevent accidental DID deactivation via explicit confirmation.  If not provided or not equal to that verbatim text, an error will be returned.",
            err=True,
        )
        raise typer.Exit(1)
    base_path = base_dir.expanduser().resolve()
    http_scheme_overrides = parse_http_scheme_overrides(http_scheme_override)
    try:
        fully_qualified_did = deactivate_did(
            did,
            base_path,
            http_scheme_overrides=http_scheme_overrides or None,
        )
        typer.echo(fully_qualified_did)
    except ControllerError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
