#!/usr/bin/env python3
"""
Fetch did:webplus microledgers from ledgerdomain.github.io and save as test fixtures.

Usage:
    uv run python scripts/fetch_ledgerdomain_fixtures.py [DID ...]

If no DIDs are provided, fetches the two known ledgerdomain DIDs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from did_webplus.did import did_to_resolution_url, parse_did
from did_webplus.http_client import fetch_did_documents_jsonl, HTTPClientError
from did_webplus.resolver import FullDIDResolver, ResolutionError, _validate_document
from did_webplus.store import SQLiteDIDDocStore

DEFAULT_DIDS = [
    "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiDBw4xANa8sR_Fd8-pv-X9A5XIJNS3tC_bRNB3HUYiKug",
    "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow",
]

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
LEDGERDOMAIN_DIR = FIXTURES_DIR / "microledgers" / "ledgerdomain"
EXPECTED_DIR = FIXTURES_DIR / "expected"


async def fetch_and_validate(did: str, *, validate: bool = True) -> tuple[str, list[str]]:
    """Fetch microledger for a DID and optionally validate. Returns (did, lines)."""
    content = await fetch_did_documents_jsonl(did)
    content = content.strip()
    if not content:
        raise ValueError(f"Empty response for {did}")

    lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
    if not lines:
        raise ValueError(f"No documents in response for {did}")

    if validate:
        prev_doc = None
        for line in lines:
            doc_dict = json.loads(line)
            try:
                _validate_document(line, doc_dict, prev_doc)
            except ResolutionError as e:
                raise ValueError(f"Validation failed for {did}: {e}") from e
            prev_doc = doc_dict

    return did, lines


async def _capture_expected_outputs(manifest_entries: list[dict]) -> None:
    """Resolve each DID and save expected resolution output to expected/."""
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        store = SQLiteDIDDocStore(db_path)
        for entry in manifest_entries:
            root_hash = entry["root_self_hash"]
            jsonl_path = LEDGERDOMAIN_DIR / f"{root_hash}.jsonl"
            lines = jsonl_path.read_text().strip().split("\n")
            lines = [ln for ln in lines if ln.strip()]
            await store.add_did_documents(lines, 0)

            resolver = FullDIDResolver(store)
            did = entry["did"]
            result = await resolver.resolve(did)

            output = {
                "didDocument": result.did_document,
                "didDocumentMetadata": {
                    "created": result.did_document_metadata.created,
                    "updated": result.did_document_metadata.updated,
                    "versionId": result.did_document_metadata.version_id,
                    "nextUpdate": result.did_document_metadata.next_update,
                    "deactivated": result.did_document_metadata.deactivated,
                },
                "didResolutionMetadata": {
                    "contentType": result.did_resolution_metadata.content_type,
                    "fetchedUpdatesFromVdr": result.did_resolution_metadata.fetched_updates_from_vdr,
                    "didDocumentResolvedLocally": result.did_resolution_metadata.did_document_resolved_locally,
                    "didDocumentMetadataResolvedLocally": result.did_resolution_metadata.did_document_metadata_resolved_locally,
                },
            }
            out_path = EXPECTED_DIR / f"{root_hash}_resolution.json"
            out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
            print(f"Captured expected output -> {out_path}")
    finally:
        db_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch ledgerdomain DIDs and save as test fixtures"
    )
    parser.add_argument(
        "dids",
        nargs="*",
        default=DEFAULT_DIDS,
        help="DIDs to fetch (default: two known ledgerdomain DIDs)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation (save raw fetch; use if validation fails due to spec differences)",
    )
    parser.add_argument(
        "--capture-expected",
        action="store_true",
        help="After fetch, save expected resolution outputs to tests/fixtures/expected/",
    )
    args = parser.parse_args()

    LEDGERDOMAIN_DIR.mkdir(parents=True, exist_ok=True)
    manifest_entries = []

    async def run() -> None:
        nonlocal manifest_entries
        for did in args.dids:
            try:
                _, lines = await fetch_and_validate(did, validate=not args.no_validate)
            except HTTPClientError as e:
                print(f"ERROR fetching {did}: {e}")
                raise SystemExit(1) from e
            except ValueError as e:
                print(f"ERROR validating {did}: {e}")
                raise SystemExit(1) from e

            components = parse_did(did)
            root_hash = components.root_self_hash
            out_path = LEDGERDOMAIN_DIR / f"{root_hash}.jsonl"

            out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            resolution_url = did_to_resolution_url(did)
            fetch_date = datetime.now(timezone.utc).isoformat()

            manifest_entries.append(
                {
                    "did": did,
                    "resolution_url": resolution_url,
                    "root_self_hash": root_hash,
                    "fetch_date": fetch_date,
                    "document_count": len(lines),
                }
            )
            print(f"Fetched {did} -> {out_path} ({len(lines)} documents)")

        manifest = {
            "fetch_date": datetime.now(timezone.utc).isoformat(),
            "entries": manifest_entries,
        }
        manifest_path = LEDGERDOMAIN_DIR / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote manifest to {manifest_path}")

        if args.capture_expected:
            await _capture_expected_outputs(manifest_entries)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
