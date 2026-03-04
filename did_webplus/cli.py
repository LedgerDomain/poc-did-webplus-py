"""CLI for did:webplus DID resolution and VDR service."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from did_webplus.did import parse_http_scheme_overrides
from did_webplus.logging_config import configure_logging
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


def _default_store_path() -> Path:
    """Default SQLite store path: ~/.did-webplus/did_documents.db"""
    return Path.home() / ".did-webplus" / "did_documents.db"


def _parse_bool_env(val: str | None) -> bool:
    """Parse env var as boolean for --no-fetch."""
    if val is None:
        return False
    return val.lower() in ("1", "true", "yes", "on")




@app.command("resolve")
def resolve_cmd(
    did: str = typer.Argument(..., help="DID to resolve (e.g. did:webplus:example.com:...)"),
    store: Path = typer.Option(
        default_factory=_default_store_path,
        path_type=Path,
        envvar="DID_WEBPLUS_STORE",
        help="Path to SQLite store (or set DID_WEBPLUS_STORE)",
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
    no_fetch: bool = typer.Option(
        False,
        "--no-fetch",
        envvar="DID_WEBPLUS_NO_FETCH",
        help="Resolve only from local store; fail if not cached (or set DID_WEBPLUS_NO_FETCH=1)",
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
    # Handle boolean from env (Typer may pass string for envvar)
    if isinstance(no_fetch, str):
        no_fetch = _parse_bool_env(no_fetch)
    elif no_fetch is None:
        no_fetch = False

    store_path = store.expanduser().resolve()
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

    result = resolver.resolve_or_result_sync(did, no_fetch=no_fetch)

    if result.did_resolution_metadata.error:
        if output == "json":
            typer.echo(json.dumps(result.to_dict(), indent=2))
        else:
            typer.echo(result.did_resolution_metadata.error, err=True)
        raise typer.Exit(1)

    if output == "json":
        out = result.to_dict()
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo("=== DID Document (JCS) ===")
        typer.echo(result.did_document)
        typer.echo("\n=== DID Document Metadata ===")
        meta = result.did_document_metadata
        typer.echo(f"  created: {meta.created}")
        typer.echo(f"  updated: {meta.updated}")
        typer.echo(f"  versionId: {meta.version_id}")
        typer.echo(f"  nextUpdate: {meta.next_update}")
        typer.echo(f"  deactivated: {meta.deactivated}")
        typer.echo("\n=== DID Resolution Metadata ===")
        res_meta = result.did_resolution_metadata
        typer.echo(f"  fetchedUpdatesFromVdr: {res_meta.fetched_updates_from_vdr}")
        typer.echo(f"  didDocumentResolvedLocally: {res_meta.did_document_resolved_locally}")


@app.command("listen")
def listen_cmd(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        envvar="DID_WEBPLUS_VDR_HOST",
        help="Host to bind (or set DID_WEBPLUS_VDR_HOST)",
    ),
    port: int = typer.Option(
        8085,
        "--port",
        "-p",
        envvar="DID_WEBPLUS_VDR_LISTEN_PORT",
        help="Port to listen on (or set DID_WEBPLUS_VDR_LISTEN_PORT)",
    ),
    store: Path = typer.Option(
        default_factory=_default_store_path,
        path_type=Path,
        envvar="DID_WEBPLUS_STORE",
        help="Path to SQLite store (or set DID_WEBPLUS_STORE)",
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
        help="Port for DIDs (optional; or set DID_WEBPLUS_VDR_DID_PORT)",
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

    store_path = store.expanduser().resolve()
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

    typer.echo(f"Starting VDR at http://{host}:{port}", err=True)
    uvicorn.run(vdr_app, host=host, port=port)


if __name__ == "__main__":
    app()
