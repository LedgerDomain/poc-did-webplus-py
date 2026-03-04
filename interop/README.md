# did:webplus Interoperability Testing

Docker-based interoperability tests between the Python implementation and the Rust reference implementation.

## Prerequisites

- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/) (for running the test script)

## Hostname Setup

The interop tests use hostnames `rust-vdr`, `rust-vdg`, and `python-vdr` for HTTP requests. Add these entries to your system's `/etc/hosts` so they resolve to localhost:

```
# Used for poc-did-webplus-py interop testing
127.0.0.1  rust-vdr
127.0.0.1  rust-vdg
127.0.0.1  python-vdr
```

On Linux/macOS, edit `/etc/hosts` with sudo (e.g. `sudo nano /etc/hosts`) and add the lines above.

## Test Matrix

| Scenario | Resolver | VDR | VDG |
|----------|----------|-----|-----|
| 1 | Python | Rust | None |
| 2 | Python | Rust | Rust |
| 3 | Rust | Python | None |
| 4 | Rust | Python | Rust |

### Test Details

Upon successful completion, each interop test scenario should print the following at the end of its output.

#### Scenario 1

```
23:12:25 interop INFO === All tests PASSED ===
23:12:25 interop INFO Summary — Scenario 1: Python resolver vs Rust VDR (no VDG)
23:12:25 interop INFO   Action: POST create — Test script submitted root DID document to Rust VDR. Expected: 200. Result: 200.
23:12:25 interop INFO   Action: PUT update — Test script submitted signed update with key rotation to Rust VDR. Expected: 200. Result: 200.
23:12:25 interop INFO   Action: GET from Rust VDR — Test script fetched did-documents.jsonl from Rust VDR. Expected: response contains latest (versionId=1). Result: PASS.
23:12:25 interop INFO   Action: Python resolver — Python resolver resolved DID via Rust VDR directly. Expected: versionId=1. Result: versionId=1.
```

#### Scenario 2

```
23:14:19 interop INFO === All tests PASSED ===
23:14:19 interop INFO Summary — Scenario 2: Python resolver vs Rust VDR + Rust VDG
23:14:19 interop INFO   Action: POST create — Test script submitted root DID document to Rust VDR. Expected: 200. Result: 200.
23:14:19 interop INFO   Action: PUT update — Test script submitted signed update with key rotation to Rust VDR. Expected: 200. Result: 200.
23:14:19 interop INFO   Action: GET from Rust VDR — Test script fetched did-documents.jsonl from Rust VDR. Expected: response contains latest (versionId=1). Result: PASS.
23:14:19 interop INFO   Action: Python resolver — Python resolver resolved DID via Rust VDG (Rust VDG proxies to Rust VDR). Expected: versionId=1. Result: versionId=1.
23:14:19 interop INFO   Action: Rust VDG headers (plain DID) — GET resolve without versionId. VDG must fetch latest from Rust VDR; X-DID-Webplus-VDG-Cache-Hit expected false. Result: PASS.
23:14:19 interop INFO   Action: Rust VDG headers (versionId param) — GET resolve with ?versionId=1. Rust VDR notified Rust VDG of updates; VDG has version; X-DID-Webplus-VDG-Cache-Hit expected true. Result: PASS.
```

#### Scenario 3

```
23:15:04 interop INFO === All tests PASSED ===
23:15:04 interop INFO Summary — Scenario 3: Rust resolver vs Python VDR (no VDG)
23:15:04 interop INFO   Action: POST create — Test script submitted root DID document to Python VDR. Expected: 200. Result: 200.
23:15:04 interop INFO   Action: PUT update — Test script submitted signed update with key rotation to Python VDR. Expected: 200. Result: 200.
23:15:04 interop INFO   Action: GET from Python VDR — Test script fetched did-documents.jsonl from Python VDR. Expected: response contains latest (versionId=1). Result: PASS.
23:15:04 interop INFO   Action: Resolver — Python resolver (stand-in for Rust) resolved DID via Python VDR directly. Expected: versionId=1. Result: versionId=1.
```

#### Scenario 4

```
23:15:43 interop INFO === All tests PASSED ===
23:15:43 interop INFO Summary — Scenario 4: Rust resolver vs Python VDR + Rust VDG
23:15:43 interop INFO   Action: POST create — Test script submitted root DID document to Python VDR. Expected: 200. Result: 200.
23:15:43 interop INFO   Action: PUT update — Test script submitted signed update with key rotation to Python VDR. Expected: 200. Result: 200.
23:15:43 interop INFO   Action: GET from Python VDR — Test script fetched did-documents.jsonl from Python VDR. Expected: response contains latest (versionId=1). Result: PASS.
23:15:43 interop INFO   Action: Resolver — Python resolver (stand-in for Rust) resolved DID via Rust VDG (Rust VDG proxies to Python VDR). Expected: versionId=1. Result: versionId=1.
23:15:43 interop INFO   Action: Rust VDG headers (plain DID) — GET resolve without versionId. VDG must fetch latest from Python VDR; X-DID-Webplus-VDG-Cache-Hit expected false. Result: PASS.
23:15:43 interop INFO   Action: Rust VDG headers (versionId param) — GET resolve with ?versionId=1. Python VDR notified Rust VDG of updates; VDG has version; X-DID-Webplus-VDG-Cache-Hit expected true. Result: PASS.
```

## Running Tests

```bash
# From the interop directory
./run_all_interop_tests.sh   # Run all 4 scenarios (convenience)

# Or run a single scenario:
./run_interop_tests.sh 1   # Scenario 1: Python resolver vs Rust VDR
./run_interop_tests.sh 2   # Scenario 2: Python resolver vs Rust VDR + VDG
./run_interop_tests.sh 3   # Scenario 3: Rust resolver vs Python VDR
./run_interop_tests.sh 4   # Scenario 4: Rust resolver vs Python VDR + VDG
```

Or run the Python script directly (with services already up):

```bash
cd ..
uv run python interop/run_interop_tests.py 1
```

## Cleanup

To stop all containers and remove volumes (guaranteed clean slate):

```bash
./stop_and_clean.sh
```

## Docker Images

- **Rust VDR**: `ghcr.io/ledgerdomain/did-webplus-vdr:v0.1.0-rc.0`
- **Rust VDG**: `ghcr.io/ledgerdomain/did-webplus-vdg:v0.1.0-rc.0`
- **Python VDR**: Built from this repo (`interop/Dockerfile.python-vdr`)

## Ports

- Rust VDR: 8085
- Rust VDG: 8086
- Python VDR: 8087
