# Test Fixtures

Test data for the did:webplus Python resolver.

## Directory Structure

- **microledgers/** — `did-documents.jsonl` samples (newline-delimited JCS DID documents)
  - **ledgerdomain/** — Fixtures fetched from ledgerdomain.github.io (see provenance below)
- **expected/** — Expected resolution outputs (JSON) for regression testing

## Ledgerdomain Fixtures (Interim)

The `microledgers/ledgerdomain/` directory contains DID microledgers fetched from the did:webplus spec authors' public VDR at `https://ledgerdomain.github.io/did-webplus-spec/`.

**Provenance:**
- Source: https://ledgerdomain.github.io/did-webplus-spec/
- Fetch date: See `manifest.json` in the ledgerdomain subdirectory
- DIDs: See `manifest.json` for the full DID strings and resolution URLs

These fixtures serve as interim test data until official test vectors arrive from LedgerDomain. Run `uv run python scripts/fetch_ledgerdomain_fixtures.py` to populate or refresh them.

## Official Test Vectors

When LedgerDomain provides the requested test vectors (see `docs/TEST_VECTOR_REQUESTS.md`), they will be added here and may supersede or supplement the interim ledgerdomain fixtures.
