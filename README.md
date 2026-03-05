# !!! PROOF OF CONCEPT ONLY -- DO NOT USE !!!

This is a PROOF OF CONCEPT ONLY Python implementation of the **Full DID Resolver** and **Verifiable Data Registry (VDR)** components the [did:webplus](https://ledgerdomain.github.io/did-webplus-spec) method, each backed by SQLite for DID document storage.

## !!! WARNING !!!

This codebase is meant to demonstrate that it is possible to have a second, interoperable implementation of (some components of) the did:webplus DID method.  It is meant ONLY AS A PROOF OF CONCEPT and should NOT BE USED in any real scenario, as the code has not been completely reviewed or fully security audited.  This codebase will not be maintained or kept up to date.  Pull requests will not be accepted.

This codebase was produced by a coding AI by pointing it at the [did:webplus spec](https://ledgerdomain.github.io/did-webplus-spec) and having it implement the DID resolver and VDR.  The AI was guided through this process by the author of the [Rust reference implementation of did:webplus](https://github.com/LedgerDomain/did-webplus) in order to produce a minimal viable demonstration of interoperability between this implementation and the Rust reference implementation.  See [interop](interop/README.md) for more on interoperability testing, including how to run it.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for package management

## Installation

```bash
uv sync
```

With dev dependencies for testing:

```bash
uv sync --extra dev
```

## Usage

### CLI

#### DID Resolution

```bash
# Resolve a DID (fetches from VDR if not cached)
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow"

# Resolve a DID at a specific versionId (fetches from VDR if not cached)
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow?versionId=1"

# Resolve a DID at a specific selfHash (fetches from VDR if not cached)
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow?selfHash=uFiAsMCOasGw6SDizP1hIvfCtwGKKNBpjU-SmTfIMi5Lc6A"

# JSON output
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow" -o json

# Offline mode (fail if not in local store)
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow" --no-fetch

# Options (can also be set via environment variables)
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow" --base-dir ./mydata --vdg-url https://vdg.example.com
```

#### DID Create/Update/Deactivate

The `did` subcommands implement a minimal DID controller: a single Ed25519 key stored under `--base-dir` (default `~/.poc-did-webplus-py`) in a subdirectory named for each controlled DID. Use `did create` to register a new DID with a VDR; it prints the DID so you can pass it to `did update` or `did deactivate`. The same `--base-dir` is used for the resolver's `did_documents.db` and the controller's keys.

```bash
# DID controller: create a new DID (prints the DID on success)
uv run did-webplus did create http://localhost:8085

# DID controller: create with custom base directory
uv run did-webplus did create http://localhost:8085 --base-dir ./mydata

# DID controller: update a DID (key rotation)
uv run did-webplus did update "did:webplus:localhost%3A8085:uFiYourRootHashHere"

# DID controller: deactivate a DID (tombstone)
uv run did-webplus did deactivate "did:webplus:localhost%3A8085:uFiYourRootHashHere"

# DID controller: use http scheme override for non-localhost VDRs
uv run did-webplus did create https://example.com:3000 --http-scheme-override example.com=http
```

#### VDR Service

```bash
# Run VDR service in listen mode.
uv run did-webplus listen --did-hostname localhost --port 8085
```

## Development

```bash
uv run pytest
```

## License

[MIT](LICENSE)
