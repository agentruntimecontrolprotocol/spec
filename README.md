# ARCP Specification

This repository contains the normative specification for the Agent Runtime Control Protocol (ARCP).

## Contents

```
docs/
  draft-arcp-1.1.md      ← normative spec
  diagrams/
    system-architecture-{light,dark}.{dot,svg}
    job-lifecycle-{light,dark}.{dot,svg}
    seq-*-{light,dark}.{puml,svg}        ← §13 example sequences
    _theme-{light,dark}.puml             ← shared PlantUML skinparams
    generate-sequences.py                ← regenerates .puml + .svg
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

The `docs/diagrams/` folder contains paired light/dark sources in two formats:

- **Graphviz `.dot`** — system architecture and job lifecycle state machine.
- **PlantUML `.puml`** — the §13 example sequence diagrams.

Regenerate SVGs with:

```sh
cd docs/diagrams

# Graphviz
for f in *.dot; do dot -Tsvg "$f" -o "${f%.dot}.svg"; done

# PlantUML sequences (writes .puml files and renders SVGs)
python3 generate-sequences.py
```

Requires `graphviz` and `plantuml`. On macOS: `brew install graphviz plantuml`. On Debian/Ubuntu: `apt-get install -y graphviz plantuml`. See [`docs/diagrams/README.md`](docs/diagrams/README.md) for the full list of diagrams.

## Contributing

Spec changes require an issue opened first with motivation and wire-shape sketch. PRs without a corresponding issue will not be merged. All contributions are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
