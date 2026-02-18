"""CLI for did:webplus DID resolution."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from did_webplus.resolver import FullDIDResolver
from did_webplus.store import SQLiteDIDDocStore

app = typer.Typer(
    name="did-webplus",
    help="Resolve did:webplus DIDs",
    add_completion=False,
)


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
    resolver = FullDIDResolver(store_impl, vdg_base_url=vdg_url)

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


if __name__ == "__main__":
    app()
