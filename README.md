# ARCP Specification

This repository contains the normative specification for the Agent Runtime Control Protocol (ARCP).

## Contents

```
docs/
  draft-arcp-1.1.md      ← normative spec
  diagrams/
    system-architecture-{light,dark}.{dot,svg}
    job-lifecycle-{light,dark}.{dot,svg}
    README.md
```

## Reading the spec

The single authoritative document is [`docs/draft-arcp-1.1.md`](docs/draft-arcp-1.1.md). It covers:

- Session lifecycle (hello/welcome, resume, heartbeats, acknowledgement, job listing, close)
- Job submission, idempotency, lifecycle, cancellation, agent versioning, and cross-session subscription
- Job event kinds and sequence number guarantees
- Result streaming (`result_chunk`)
- Lease capability model, namespaces, subsetting, expiration, and budget enforcement
- Delegation
- Trace propagation (W3C Trace Context)
- Error taxonomy
- Security considerations
- IANA considerations

## Diagrams

The `docs/diagrams/` folder contains paired light/dark Graphviz sources for the system architecture and job lifecycle state machine. Edit the `.dot` files; regenerate SVGs with:

```sh
cd docs/diagrams
for f in *.dot; do dot -Tsvg "$f" -o "${f%.dot}.svg"; done
```

Requires `graphviz`. On macOS: `brew install graphviz`. On Debian/Ubuntu: `apt-get install -y graphviz`.

## Contributing

Spec changes require an issue opened first with motivation and wire-shape sketch. PRs without a corresponding issue will not be merged. All contributions are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
