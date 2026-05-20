#!/usr/bin/env python3
"""Generate paired light/dark PlantUML sequence diagrams for ARCP examples.

Run from this directory. Produces `<name>-{light,dark}.puml` and renders
both to SVG via `plantuml`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Body content per diagram. Each body uses theme-provided variables:
#   $client_color  participant tint for the primary client
#   $peer_color    secondary client / dashboard tint
#   $gateway_color upstream gateway tint
#   $client_arrow  outbound client->router arrow
#   $reply_arrow   router->client reply arrow
#   $muted_arrow   replay / low-emphasis arrow
#   $accent_arrow / $accent_text   terminal `job.result` highlight
#   $error_arrow  / $error_text    error / lease-expiry highlight
#   $success_arrow/ $success_text  success highlight
DIAGRAMS: dict[str, str] = {
    "seq-heartbeat-liveness": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R

== quiet period: 30s elapse ==

C -[$client_arrow]>  R : session.ping\n{ nonce: "p1", sent_at: "...:43:00Z" }
R -[$reply_arrow]-> C : session.pong\n{ ping_nonce: "p1", received_at: "...:43:00.020Z" }

== another 30s elapse ==

R -[$reply_arrow]>  C : session.ping\n{ nonce: "p2", sent_at: "...:43:30Z" }
C -[$client_arrow]-> R : session.pong\n{ ping_nonce: "p2", received_at: "...:43:30.015Z" }

note over C, R
  Missing pong within 30s closes the transport
  and surfaces HEARTBEAT_LOST. Jobs keep running
  server-side and may be resumed within the
  resume window.
end note
""",
    "seq-event-ack-backpressure": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R

C -[$client_arrow]>  R : job.submit\n{ agent: "log-tail", ... }
R -[$reply_arrow]-> C : job.accepted\n{ job_id: job_LT }

group rapid burst
  R -[$reply_arrow]-> C : job.event [seq=1..100]
end
C -[$client_arrow]>  R : session.ack\n{ last_processed_seq: 12 }

group continues
  R -[$reply_arrow]-> C : job.event [seq=101..200]
end
C -[$client_arrow]>  R : session.ack\n{ last_processed_seq: 28 }

R -[$reply_arrow]-> C : job.event [seq=201..300]

note right of R
  runtime detects lag > threshold
end note

R -[$accent_arrow]-> C : <color:$accent_text>job.event [seq=301]</color>\n{ kind: "status",\n  body: { phase: "back_pressure",\n          message: "consumer lag 270 events" } }
""",
    "seq-job-list-subscribe": r"""
participant "<color:white>Client C2</color>" as C2 $peer_color
participant "Router R" as R

C2 -[$client_arrow]>  R  : session.hello
R  -[$reply_arrow]-> C2 : session.welcome\n{ session_id: sess_B2 }

C2 -[$client_arrow]>  R  : session.list_jobs\n{ status: ["running"] }
R  -[$reply_arrow]-> C2 : session.jobs\n{ job_R1, last_event_seq: 84 }

C2 -[$client_arrow]>  R  : job.subscribe\n{ history: true, from_event_seq: 0 }
R  -[$reply_arrow]-> C2 : job.subscribed\n{ subscribed_from: 84, replayed: true }

group replay (body.ts preserved, session-scoped seq)
  R -[$muted_arrow]-> C2 : job.event [seq=1..84]
end

== live ==

R -[$reply_arrow]-> C2 : job.event [seq=85..]
R -[$accent_arrow]-> C2 : <color:$accent_text>job.result</color> [seq=N]
""",
    "seq-lease-expiration": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R

C -[$client_arrow]>  R : job.submit\n{ agent: "indexer",\n  lease_request: { fs.read: ["/data/**"],\n                   fs.write: ["/index/**"] },\n  lease_constraints: { expires_at: "2026-05-13T20:00:00Z" } }
R -[$reply_arrow]-> C : job.accepted\n{ job_id: job_IX,\n  lease_constraints: { expires_at: "...20:00:00Z" } }

R -[$reply_arrow]-> C : job.event [seq=N]\n{ kind: "progress",\n  body: { current: 42000, total: 100000, units: "files" } }

== 20:00:00 UTC arrives — job still running ==

R -[$error_arrow]-> C : <color:$error_text>job.event [seq=N+1]</color>\n{ kind: "tool_result",\n  body: { call_id: c_42001,\n          error: { code: "LEASE_EXPIRED",\n                   message: "Lease expired at 20:00:00Z",\n                   retryable: false } } }
R -[$error_arrow]-> C : <color:$error_text>job.error [seq=N+2]</color>\n{ final_status: "error",\n  code: "LEASE_EXPIRED",\n  message: "Lease expired during execution" }
""",
    "seq-budget-enforcement": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R

C -[$client_arrow]>  R : job.submit\n{ agent: "web-research",\n  lease_request: { tool.call: ["search.*", "fetch.*"],\n                   cost.budget: ["USD:1.00"] } }
R -[$reply_arrow]-> C : job.accepted\n{ job_id: job_WR, budget: { USD: 1.00 } }

group call 1 — search ($0.42)
  R -[$reply_arrow]-> C : job.event [seq=1] tool_call search.web c1
  R -[$reply_arrow]-> C : job.event [seq=2] tool_result c1
  R -[$reply_arrow]-> C : job.event [seq=3] metric cost.search 0.42 USD
  R -[$reply_arrow]-> C : job.event [seq=4] metric cost.budget.remaining 0.58 USD
end

group call 2 — fetch ($0.70 → over budget)
  R -[$reply_arrow]-> C : job.event [seq=5] tool_call fetch.url c2
  R -[$reply_arrow]-> C : job.event [seq=6] tool_result c2
  R -[$reply_arrow]-> C : job.event [seq=7] metric cost.fetch 0.70 USD
  R -[$reply_arrow]-> C : job.event [seq=8] metric cost.budget.remaining -0.12 USD
end

group call 3 — rejected
  R -[$reply_arrow]-> C : job.event [seq=9] tool_call fetch.url c3
  R -[$error_arrow]-> C : <color:$error_text>job.event [seq=10]</color>\n{ kind: "tool_result",\n  body: { call_id: c3,\n          error: { code: "BUDGET_EXHAUSTED",\n                   message: "USD budget exhausted",\n                   retryable: false } } }
end
""",
    "seq-streamed-result": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R

R -[$reply_arrow]-> C : job.event [seq=1..40]  (intermediate work)

group chunked result emission (result_id = res_RP1)
  R -[$reply_arrow]-> C : job.event [seq=41] result_chunk\n{ chunk_seq: 0, data: "...first 1 MB...",\n  encoding: "utf8", more: true }
  R -[$reply_arrow]-> C : job.event [seq=42..70] (more chunks)
  R -[$reply_arrow]-> C : job.event [seq=71] result_chunk\n{ chunk_seq: 30, data: "...final chunk...",\n  encoding: "utf8", more: false }
end

R -[$success_arrow]-> C : <color:$success_text>job.result [seq=72]</color>\n{ final_status: "success",\n  result_id: "res_RP1",\n  result_size: 31_457_280,\n  summary: "Report generated, 31 MB, 31 chunks." }

note over C, R
  Client accumulates chunks by result_id and assembles
  the final result. session.ack backpressure (§6.5) is
  particularly important during chunked emission.
end note
""",
    "seq-provisioned-credential": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R
participant "<color:white>Gateway</color>" as G $gateway_color

C -[$client_arrow]>  R : job.submit\n{ agent: "research-summarizer",\n  lease_request: { tool.call: ["fetch.*"],\n                   cost.budget: ["USD:2.00"],\n                   model.use: ["tier-fast/*"] } }

R -[$muted_arrow]>  G : provision scoped credential\n(max_budget=$2.00,\n allowed_models=tier-fast/*,\n ttl=lease.expires_at)
G -[$muted_arrow]-> R : { value: "sk-virt-abc...", id: "vk_42" }

R -[$reply_arrow]-> C : job.accepted\n{ job_id: job_RS, budget: { USD: 2.00 },\n  credentials: [ { id: "cred_01J...",\n                   scheme: "bearer",\n                   value: "sk-virt-abc...",\n                   endpoint: "https://gw.example/v1",\n                   profile: "openai",\n                   constraints: {\n                     "cost.budget": ["USD:2.00"],\n                     "model.use":   ["tier-fast/*"] } } ] }

== agent calls gateway directly with sk-virt-abc... ==

note over G
  Gateway enforces budget and
  model tier independently.
end note

R -[$reply_arrow]-> C : job.event [seq=N] metric cost.inference 0.83 USD
R -[$success_arrow]-> C : <color:$success_text>job.result [seq=M]</color>\n{ final_status: "success", ... }

R -[$muted_arrow]>  G : revoke vk_42
""",
    "seq-agent-versioning": r"""
participant "<color:white>Client C</color>" as C $client_color
participant "Router R" as R

C -[$client_arrow]>  R : session.hello
R -[$reply_arrow]-> C : session.welcome\n{ capabilities: { agents: [\n    { name: "code-refactor",\n      versions: ["1.0.0", "2.0.0"],\n      default: "2.0.0" } ] } }

C -[$client_arrow]>  R : job.submit\n{ agent: "code-refactor@1.0.0", ... }
R -[$reply_arrow]-> C : job.accepted\n{ job_id: job_CR }

== later — attempting an unavailable version ==

C -[$client_arrow]>  R : job.submit\n{ agent: "code-refactor@3.0.0", ... }
R -[$error_arrow]-> C : <color:$error_text>session.error</color>\n{ code: "AGENT_VERSION_NOT_AVAILABLE",\n  message: "code-refactor@3.0.0 not registered",\n  retryable: false }
""",
}


def emit(name: str, theme: str, body: str) -> Path:
    """Write a <name>-<theme>.puml file and return its path."""
    out = HERE / f"{name}-{theme}.puml"
    contents = (
        "@startuml\n"
        f"!include _theme-{theme}.puml\n"
        f"{body.strip()}\n"
        "@enduml\n"
    )
    out.write_text(contents)
    return out


def main() -> int:
    written: list[Path] = []
    for name, body in DIAGRAMS.items():
        for theme in ("light", "dark"):
            written.append(emit(name, theme, body))

    print(f"wrote {len(written)} .puml files; rendering SVGs...")
    cmd = ["plantuml", "-tsvg", *[str(p.name) for p in written]]
    result = subprocess.run(cmd, cwd=HERE)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
