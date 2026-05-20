# Diagrams

Paired light/dark diagrams for the ARCP specification. Two source
formats are used:

- **Graphviz (`.dot`)** for the system architecture and job lifecycle
  state machine.
- **PlantUML (`.puml`)** for the example sequence diagrams in §13 of
  the spec.

Sequence-diagram `.puml` files are generated from a single
source-of-truth Python module (`generate-sequences.py`) so that the
light and dark variants stay in sync. Edit the body content there;
the script writes the `.puml` files and renders them to SVG.

## System architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="system-architecture-dark.svg">
  <img alt="ARCP system architecture" src="system-architecture-light.svg">
</picture>

## Job lifecycle

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="job-lifecycle-dark.svg">
  <img alt="ARCP job lifecycle FSM" src="job-lifecycle-light.svg">
</picture>

## Sequence diagrams (spec §13 examples)

| Example | Source |
|---|---|
| §13.1 Heartbeat liveness | `seq-heartbeat-liveness-{light,dark}.puml` |
| §13.2 Event acknowledgement and slow consumer | `seq-event-ack-backpressure-{light,dark}.puml` |
| §13.3 Job listing and subscription | `seq-job-list-subscribe-{light,dark}.puml` |
| §13.4 Lease expiration | `seq-lease-expiration-{light,dark}.puml` |
| §13.5 Budget enforcement | `seq-budget-enforcement-{light,dark}.puml` |
| §13.6 Streamed result | `seq-streamed-result-{light,dark}.puml` |
| §13.7 Provisioned credential | `seq-provisioned-credential-{light,dark}.puml` |
| §13.8 Agent versioning | `seq-agent-versioning-{light,dark}.puml` |

Both themes share `_theme-light.puml` and `_theme-dark.puml`, which
define the shared skinparams and a palette of named colors
(`$client_arrow`, `$accent_text`, etc.) referenced from each
diagram body.

## Render

```sh
cd spec/docs/diagrams

# Graphviz diagrams
for f in *.dot; do dot -Tsvg "$f" -o "${f%.dot}.svg"; done

# PlantUML sequence diagrams (regenerates .puml files and renders SVGs)
python3 generate-sequences.py
```

Dependencies:

- `graphviz` provides `dot`. macOS: `brew install graphviz`. Debian/Ubuntu:
  `apt-get install -y graphviz`.
- `plantuml` (which pulls in a JRE). macOS: `brew install plantuml`.
  Debian/Ubuntu: `apt-get install -y plantuml`.
