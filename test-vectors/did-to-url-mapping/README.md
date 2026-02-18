# DID-to-URL Mapping

Per the did:webplus spec (Draft v0.4), the mapping steps are:

1. If domain is `localhost`, prepend `http://`; otherwise prepend `https://`
2. Append `/did-documents.jsonl`
3. Percent-decode (for port, e.g. `%3A` -> `:`)
4. Replace all `:` with `/`
5. Drop `did:webplus:` prefix

Path components in the DID (colon-delimited) become path segments (slash-delimited) in the URL.
