# did-webplus Python Full DID Resolver

A Python implementation of the **Full DID Resolver** for the [did:webplus](https://ledgerdomain.github.io/did-webplus-spec) method, backed by SQLite for DID document storage.

## Features

- Full verification: self-hash, chain integrity, JWS proofs, and update rules evaluation
- Offline resolution when documents are cached
- Historical resolution by `selfHash` or `versionId` query parameters
- Optional VDG (Verifiable Data Gateway) support for fetching via VDG instead of VDR
- SQLite-backed DID document store

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

### Python SDK

`did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow` is a real DID, so this 

```python
from did_webplus import FullDIDResolver, SQLiteDIDDocStore

# Create store and resolver
store = SQLiteDIDDocStore("did_documents.db")
resolver = FullDIDResolver(store)

# Optional: use VDG for fetching
# resolver = FullDIDResolver(store, vdg_base_url="https://vdg.example.com")

# Async resolve (latest)
result = await resolver.resolve("did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow")

# Sync resolve (for scripts and non-async apps)
result = resolver.resolve_sync("did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow")

# Resolve by versionId or selfHash
result = await resolver.resolve("did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow?versionId=1")
result = await resolver.resolve("did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow?selfHash=uFiAsMCOasGw6SDizP1hIvfCtwGKKNBpjU-SmTfIMi5Lc6A")

# Result: did_document (JCS string), did_document_metadata, did_resolution_metadata
# W3C-style output: result.to_dict() → {didResolutionMetadata, didDocument, didDocumentMetadata}
```

### CLI

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
uv run did-webplus resolve "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow" --store ./mydb.db --vdg-url https://vdg.example.com

# Run VDR service in listen mode.
uv run did-webplus listen --did-hostname localhost --port 8085
```

## Development

```bash
uv run pytest
```

## License

MIT
