# Test Vector Requests for did:webplus Python Resolver

This document describes the test vectors requested from the did:webplus reference implementors (LedgerDomain) to support comprehensive testing of the Python Full DID Resolver implementation. These requests can be filed as an issue at [LedgerDomain/did-webplus](https://github.com/LedgerDomain/did-webplus) or shared directly with the maintainers.

## Purpose

The Python implementation needs canonical, spec-compliant test vectors to validate:
- Self-hash computation and verification
- DID document chain validation (root and non-root)
- JWS proof verification and update rules evaluation
- End-to-end resolution output format

## Requested Test Vectors

### 1. Canonical DID Documents (Valid)

- **Root DID document**: A single valid root DID document in JCS form, including:
  - The exact JCS string (canonical JSON)
  - The expected `selfHash` value
  - Verification methods and `capabilityInvocation`
  - `updateRules` (e.g. `{"key": "..."}` or `{"any": [...]}`)
  - `proofs` array with at least one valid JWS (if root documents include proofs)
- **Non-root DID document**: A valid non-root document chained to the root, including:
  - The exact JCS string
  - The expected `selfHash` value
  - `prevDIDDocumentSelfHash` matching the root's `selfHash`
  - Valid `proofs` that satisfy the root's `updateRules`

### 2. Microledger Samples

- A complete `did-documents.jsonl` file (newline-delimited JCS) for a DID with 2+ documents
- The DID string that corresponds to this microledger
- The resolution URL for this DID

### 3. Negative Cases (Invalid / Rejection Expected)

- **Invalid self-hash**: A document where the `selfHash` field does not match the computed hash
- **Invalid chain**: A non-root document whose `prevDIDDocumentSelfHash` does not match the previous document
- **Invalid versionId**: Non-root document with `versionId` not equal to `prev.versionId + 1`
- **Invalid validFrom**: Non-root document with `validFrom` <= previous document's `validFrom`
- **Invalid proofs**: Document with JWS proof that fails verification (wrong signature, wrong payload, etc.)
- **Unsatisfied update rules**: Non-root document whose proofs do not satisfy the previous document's `updateRules`
- **Malformed update rules**: Document with invalid `updateRules` structure

### 4. Resolution Expectations

For a given DID (with and without `?selfHash=...` and `?versionId=...` query params):
- Expected `didDocument` (JCS string)
- Expected `didDocumentMetadata` (created, updated, versionId, deactivated, etc.)
- Expected `didResolutionMetadata` (contentType, fetchedUpdatesFromVdr, didDocumentResolvedLocally)

### 5. Update Rules Variants

Sample documents or rules covering:
- `{"key": "..."}` (base64url multicodec public key)
- `{"hashedKey": "..."}` (MBHash)
- `{"any": [...]}`
- `{"all": [...]}`
- `{"atLeast": N, "of": [...]}` with `{"weight": W, ...}`

## Optional

- Deactivated DID document (tombstone with `updateRules: {}`)
- DID with path components (e.g. `did:webplus:example.com:path:rootHash`)
- DID with port (e.g. `did:webplus:example.com%3A3000:rootHash`)
