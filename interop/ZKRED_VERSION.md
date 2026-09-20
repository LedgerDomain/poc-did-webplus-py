# `@zkred/did-webplus` version card

Pinned versioning is intentional: a committed lockfile keeps CI/repros stable, while (e.g.) `^X.Y.Z` in `package.json` allows deliberate bumps via PR. Re-review the package on each lockfile bump (changelog, install scripts, transitive deps). There is no automatic upgrade path.

## Commands

```bash
cd interop

# Check which version will run (lockfile + installed package file)
grep '"@zkred/did-webplus"' package.json package-lock.json
node -e "console.log(JSON.parse(require('fs').readFileSync('node_modules/@zkred/did-webplus/package.json','utf8')).version)"
# Or from the Docker image (override entrypoint; image ENTRYPOINT is ts_runner.mjs):
docker run --rm --entrypoint node did-webplus-zkred -e \
  "console.log(JSON.parse(require('fs').readFileSync('node_modules/@zkred/did-webplus/package.json','utf8')).version)"

# Bump to a new release (then commit package.json + package-lock.json)
npm install @zkred/did-webplus@<version>
# Update the pinned version line at the top of this file in the same PR.
# ./run.sh rebuilds did-webplus-zkred automatically on the next matrix/vectors/scenarios run.

# Run TS scenarios
./run.sh matrix 17
./run.sh matrix
```

Full operator guide: [README.md § TypeScript implementation](README.md#typescript-implementation-zkreddid-webplus--version-management).
