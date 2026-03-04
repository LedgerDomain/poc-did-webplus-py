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

## Running Tests

```bash
# From the interop directory
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
