---
name: Pre-Test-Vector Work Plan
overview: Prepare test infrastructure and fetch existing ledgerdomain DIDs as fixtures before official test vectors arrive. This includes creating the fixture layout, a fetch script, storing the two known DIDs, and adding tests that use real fetched data.
todos: []
isProject: false
---

# Pre-Test-Vector Work Plan

Work that can be done before receiving the official test vectors from LedgerDomain, including fetching and storing the two existing online DIDs as test fixtures.

## 1. Create Fixture Directory Structure

Create the fixture layout described in the existing plan ([.cursor/plans/did-webplus_full_resolver_python_7bad1c7d.plan.md](.cursor/plans/did-webplus_full_resolver_python_7bad1c7d.plan.md)):

```
tests/
├── fixtures/
│   ├── microledgers/          # did-documents.jsonl samples
│   │   └── ledgerdomain/      # Fetched from ledgerdomain.github.io
│   └── expected/              # Expected resolution outputs (JSON)
```

Add a `README.md` in `tests/fixtures/` documenting:

- Purpose of each subdirectory
- Provenance of ledgerdomain fixtures (source URL, fetch date)
- That official test vectors will be added when received

## 2. Fetch Script for Ledgerdomain DIDs

Create `scripts/fetch_ledgerdomain_fixtures.py` that:

- Uses existing `[did_webplus.http_client.fetch_did_documents_jsonl](did_webplus/http_client.py)` to fetch from the resolution URLs
- Accepts DIDs as arguments (or uses the two known DIDs by default)
- Validates fetched content via `FullDIDResolver` (or `_validate_document` logic) to ensure it passes self-hash, chain, and proof verification
- Writes each DID's microledger to `tests/fixtures/microledgers/ledgerdomain/{root_self_hash}.jsonl` (or a similar naming scheme)
- Writes a manifest `tests/fixtures/microledgers/ledgerdomain/manifest.json` with: DID, resolution URL, fetch date, document count

Resolution URLs for the two DIDs (from `[did_webplus.did.did_to_resolution_url](did_webplus/did.py)`):

- `did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiDBw4xANa8sR_Fd8-pv-X9A5XIJNS3tC_bRNB3HUYiKug`  
→ `https://ledgerdomain.github.io/did-webplus-spec/uFiDBw4xANa8sR_Fd8-pv-X9A5XIJNS3tC_bRNB3HUYiKug/did-documents.jsonl`
- `did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow`  
→ `https://ledgerdomain.github.io/did-webplus-spec/uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow/did-documents.jsonl`

## 3. Run Fetch and Store Fixtures

Execute the script to populate `tests/fixtures/microledgers/ledgerdomain/` with:

- `uFiDBw4xANa8sR_Fd8-pv-X9A5XIJNS3tC_bRNB3HUYiKug.jsonl`
- `uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow.jsonl`
- `manifest.json`

## 4. Add Conftest Fixtures for Ledgerdomain Data

In [tests/conftest.py](tests/conftest.py):

- Add `ledgerdomain_fixtures` fixture that loads the manifest and returns paths to the JSONL files
- Add `ledgerdomain_did_1` and `ledgerdomain_did_2` fixtures (or a parametrized list) with the full DID strings and corresponding fixture paths

## 5. Add Resolver Tests Using Fixtures

Extend [tests/test_resolver_integration.py](tests/test_resolver_integration.py):

- **Test: resolve from fixture (no network)**: Load JSONL from fixture, seed the store, resolve the DID. Assert `did_document`, `version_id`, metadata. No HTTP mock needed.
- **Test: full chain validation**: For each ledgerdomain fixture, parse each line, run `_validate_document` (or equivalent) to ensure our validation accepts the real data.
- **Test: query params**: Resolve with `?versionId=0` and `?selfHash=...` using fixture data.

These tests validate that our implementation correctly processes real did:webplus documents from the spec authors.

## 6. Capture Expected Resolution Outputs (Optional)

For each ledgerdomain DID, run resolution and save to `tests/fixtures/expected/`:

- `{root_hash}_resolution.json` with `didDocument`, `didDocumentMetadata`, `didResolutionMetadata`

This provides a baseline for future comparison when official vectors arrive and for regression testing.

## 7. Document in TEST_VECTOR_REQUESTS.md

Add a short section to [docs/TEST_VECTOR_REQUESTS.md](docs/TEST_VECTOR_REQUESTS.md):

- "Interim fixtures": We are using the two existing ledgerdomain DIDs as interim test data until official vectors arrive.
- List the DIDs and their source URLs.
- Note that official vectors will supersede or supplement these when received.

## Summary of New/Modified Files


| Action | Path                                                                         |
| ------ | ---------------------------------------------------------------------------- |
| Create | `tests/fixtures/README.md`                                                   |
| Create | `tests/fixtures/microledgers/ledgerdomain/.gitkeep` (or populated by script) |
| Create | `scripts/fetch_ledgerdomain_fixtures.py`                                     |
| Modify | `tests/conftest.py`                                                          |
| Modify | `tests/test_resolver_integration.py`                                         |
| Modify | `docs/TEST_VECTOR_REQUESTS.md`                                               |


## Dependencies

- No new dependencies. Uses existing `httpx`, `FullDIDResolver`, and `fetch_did_documents_jsonl`.
- Fetch script can be run with `python scripts/fetch_ledgerdomain_fixtures.py` (or `uv run python ...`).

## Risk / Fallback

If the ledgerdomain URLs are unreachable or return unexpected content during fetch:

- Script should fail clearly with an error message.
- Tests that depend on fixtures can be skipped when fixtures are missing (e.g. `pytest.importorskip` or `Path.exists()` check).
- Document in README that fixtures must be fetched before running fixture-based tests.

