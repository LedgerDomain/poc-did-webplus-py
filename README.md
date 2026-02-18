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

```python
from did_webplus import FullDIDResolver, SQLiteDIDDocStore

# Create store and resolver
store = SQLiteDIDDocStore("did_documents.db")
resolver = FullDIDResolver(store)

# Optional: use VDG for fetching
# resolver = FullDIDResolver(store, vdg_base_url="https://vdg.example.com")

# Resolve a DID (latest)
result = await resolver.resolve("did:webplus:example.com:EjXivDidxAi2kETdFw1o36-jZUkYkxg0ayMhSBjODAgQ")

# Resolve by versionId
result = await resolver.resolve("did:webplus:example.com:EjXivDidxAi2kETdFw1o36-jZUkYkxg0ayMhSBjODAgQ?versionId=1")

# Resolve by selfHash
result = await resolver.resolve("did:webplus:example.com:EjXivDidxAi2kETdFw1o36-jZUkYkxg0ayMhSBjODAgQ?selfHash=EgqvDOcj4HItWDVij-yHj0GtBPnEofatHT2xuoVD7tMY")

# Result contains: did_document, did_document_metadata, did_resolution_metadata
```

## Development

```bash
uv run pytest
```

## License

MIT
