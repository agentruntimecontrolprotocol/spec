# ARCP: Agent Runtime Control Protocol

```
Internet-Draft                                           [Author Name]
Intended status: Standards Track                                  ARCP
Expires: November 13, 2026                                 May 13, 2026
```

**Agent Runtime Control Protocol (ARCP) — Version 1.0**

## Status of This Memo

This document is a draft specification distributed for review and
discussion. It is not yet an approved standard. Implementations are
encouraged but should expect breaking changes before v1.0 is finalized.

Distribution of this memo is unlimited.

## Abstract

The Agent Runtime Control Protocol (ARCP) is a transport-agnostic
wire protocol for submitting, observing, and controlling long-running
AI agent jobs. ARCP provides durable job identity, resumable event
streams, capability-based authority via leases, and structured
agent-to-agent delegation, while remaining agnostic about how agents
are implemented or what tools they invoke.

ARCP complements rather than replaces existing agent-facing protocols.
Tool exposure remains the concern of protocols such as the Model
Context Protocol (MCP); ARCP defines what happens around tool calls —
the surrounding execution, durability, and authorization context.

## Table of Contents

1. Introduction
   1.1. Scope
   1.2. Non-Goals
   1.3. Relationship to Other Protocols
2. Conventions
   2.1. Requirements Language
   2.2. Terminology
3. Protocol Overview
4. Transport
5. Wire Format
6. Sessions
7. Jobs
8. Job Events
9. Leases
10. Delegation
11. Trace Propagation
12. Error Taxonomy
13. Examples
14. Security Considerations
15. IANA Considerations
16. References

---

## 1. Introduction

AI agent systems increasingly run long-lived, multi-step workloads that
outlive a single network connection, span multiple cooperating agents,
and must operate within bounded authority. Existing protocols address
adjacent concerns — exposing tools to agents (MCP), exchanging chat
completions (OpenAI-compatible APIs), workflow orchestration (Temporal,
Restate) — but none provide a transport-level contract for *running* an
agent job with durability, resumability, and capability-bounded
delegation as first-class primitives.

ARCP fills this gap. It defines:

- A canonical envelope and message set for agent job control.
- Durable jobs with stable identity across reconnects.
- Resumable, ordered event streams indexed by monotonic sequence numbers.
- A capability-based lease model that constrains what a job (and any
  jobs it delegates to) may do.
- W3C Trace Context propagation across delegation boundaries.
- A canonical error taxonomy enabling deterministic client handling.

### 1.1. Scope

ARCP specifies:

- The wire format for client-runtime communication.
- The lifecycle of sessions, jobs, and event streams.
- The authority model (leases) and its enforcement requirements.
- The mechanics of agent-to-agent delegation within a runtime.
- Trace context propagation rules.

### 1.2. Non-Goals

ARCP does **not** specify:

- How agents are implemented internally.
- How tools are exposed to agents (use MCP or equivalent).
- How human-in-the-loop interactions are surfaced (use a dedicated
  HITL protocol; the agent invokes it as a tool).
- How agent state is persisted across process restarts. ARCP requires
  that the runtime survive transport drops; full process-level
  durability is a runtime implementation concern (e.g., backed by
  Temporal, Restate, or a custom checkpoint system).
- Telemetry export formats. Runtimes SHOULD use OpenTelemetry.
- Authentication mechanisms beyond bearer tokens. Higher-level identity
  (OAuth, mTLS) is a deployment concern.

### 1.3. Relationship to Other Protocols

ARCP operates *around* tool calls, not *as* a tool protocol:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/system-architecture-dark.svg">
  <img alt="ARCP system architecture — Runtime Host with ARCP, Agent Processes (as MCP clients), and MCP servers; ARCP Client connects via ARCP" src="diagrams/system-architecture-light.svg">
</picture>

A single trace, identified by a W3C `trace_id`, MAY span an ARCP job,
its delegated sub-jobs, and any MCP tool invocations those jobs make.

---

## 2. Conventions

### 2.1. Requirements Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [RFC2119] and
[RFC8174].

### 2.2. Terminology

- **Client**: An entity that opens an ARCP session and submits jobs.
  Examples include CLIs, IDEs, dashboards, and supervisory services.
- **Runtime**: The ARCP server. Hosts agents and executes jobs.
- **Session**: An authenticated, resumable connection between a client
  and a runtime.
- **Job**: A durable unit of agent work with stable identity, an
  immutable lease, and a streamed event log.
- **Agent**: A named, runtime-registered capability that executes
  jobs. The unit a client submits work to.
- **Event**: A server-to-client message emitted during job execution
  carrying logs, intermediate results, delegation requests, or status
  changes.
- **Lease**: The immutable set of capabilities granted to a job at
  submission time.
- **Capability**: A named permission such as `fs.read` paired with
  one or more pattern constraints.
- **Delegation**: A running job's request to start a sub-job whose
  lease is a subset of the parent's.

---

## 3. Protocol Overview

### 3.1. Lifecycle

A typical ARCP interaction:

1. Client opens a transport connection to the runtime.
2. Client sends `session.hello` with credentials and capabilities.
3. Runtime responds with `session.welcome`, assigning a `session_id`
   and `resume_token`.
4. Client sends `job.submit` describing the agent, input, and
   requested lease. Runtime responds with `job.accepted` carrying a
   `job_id`.
5. Runtime emits `job.event` messages as the job runs. Each event
   carries a monotonic `event_seq` scoped to the session.
6. The job terminates with `job.result` (success) or `job.error`
   (failure). The client MAY cancel before termination via `job.cancel`.
7. Client closes the connection with `session.bye`, or the transport
   drops. In the latter case, the client MAY reconnect and resume
   (Section 6.3) provided it has retained `(session_id, resume_token,
   last_event_seq)`.

---

## 4. Transport

ARCP is transport-agnostic at the message-set level. Conformant
implementations MUST support at least one of the following transports
in each role:

### 4.1. WebSocket (Mandatory for Network Deployments)

For network-reachable runtimes, ARCP messages MUST be carried over
WebSocket [RFC6455] using text frames containing JSON payloads. TLS
[RFC8446] MUST be used (`wss://`). The default URL path is `/arcp`.

### 4.2. stdio (Mandatory for In-Process Children)

For in-process or subprocess runtimes (typical of agents running as
child processes of an IDE or supervisor), ARCP messages MUST be
exchanged as newline-delimited JSON over the child's stdin/stdout.
Each line is exactly one ARCP envelope (Section 5.1) with no embedded
newlines in the JSON encoding.

### 4.3. Other Transports

HTTP/2 streams, QUIC, and message queue (MQ) bindings MAY be supported
as optional transports. Implementations supporting alternate transports
MUST preserve identical message semantics, ordering guarantees, and
sequence number behavior described elsewhere in this document.

---

## 5. Wire Format

### 5.1. Envelope

Every ARCP message is a JSON object conforming to the following
envelope schema:

```json
{
  "arcp":       "1",
  "id":         "01JABCDEFGHJKMNPQRSTVWXYZ",
  "type":       "<message type>",
  "session_id": "sess_...",
  "trace_id":   "<W3C trace-id, optional pre-welcome>",
  "job_id":     "<job_id, when applicable>",
  "event_seq":  <integer, when applicable>,
  "payload":    { ... }
}
```

Field definitions:

- `arcp` (string, REQUIRED): Protocol version. MUST be `"1"` for this
  specification.
- `id` (string, REQUIRED): Per-message unique identifier. SHOULD be a
  ULID or UUIDv7. Used by transport-level deduplication and
  acknowledgement.
- `type` (string, REQUIRED): The message type. See Sections 6–10.
- `session_id` (string, REQUIRED after welcome): Identifies the
  session. Absent only on `session.hello` and the corresponding
  `session.welcome`.
- `trace_id` (string, OPTIONAL): W3C Trace Context trace-id (16-byte
  hex). When set, links the message to a distributed trace.
- `job_id` (string, REQUIRED when applicable): Identifies the job
  for job-scoped messages.
- `event_seq` (integer, REQUIRED on `job.event`, `job.result`,
  `job.error`): Monotonic, session-scoped sequence number.
- `payload` (object, REQUIRED): Type-specific message body.

Unknown top-level fields MUST be ignored by implementations to allow
forward-compatible extensions.

### 5.2. Encoding

JSON [RFC8259] is the only encoding defined in this specification.
Future versions MAY negotiate alternate encodings (e.g., CBOR) via the
`session.hello` capabilities field.

String fields MUST be UTF-8. Integer fields MUST fit in a signed
64-bit integer.

---

## 6. Sessions

### 6.1. Authentication

The client authenticates by presenting a bearer token in the
`session.hello` payload. Token format and issuance are deployment
concerns. Runtimes MUST reject `session.hello` messages missing or
presenting an invalid token with `session.error` and immediate transport
close.

### 6.2. Hello / Welcome

**Client → Runtime:**

```json
{
  "arcp": "1",
  "id": "01J...",
  "type": "session.hello",
  "payload": {
    "client":       { "name": "examplectl", "version": "0.4.1" },
    "auth":         { "scheme": "bearer", "token": "..." },
    "capabilities": { "encodings": ["json"] }
  }
}
```

**Runtime → Client:**

```json
{
  "arcp": "1",
  "id": "01J...",
  "type": "session.welcome",
  "session_id": "sess_01JABCDEFGHJKMNPQ",
  "payload": {
    "runtime":      { "name": "example-runtime", "version": "1.2.0" },
    "resume_token": "rt_4f8c...",
    "resume_window_sec": 600,
    "capabilities": {
      "encodings": ["json"],
      "agents":    ["code-refactor", "test-runner", "report-generator"]
    }
  }
}
```

The runtime MUST issue a `resume_token` opaque to the client. The
client MUST treat it as a credential and store it with the same care
as the original bearer token. The runtime MUST guarantee that a
session can be resumed for at least `resume_window_sec` seconds after
the most recent message.

### 6.3. Resume

To resume a dropped session, the client connects a new transport and
sends `session.hello` including a `resume` block:

```json
{
  "type": "session.hello",
  "payload": {
    "client":       { "name": "examplectl", "version": "0.4.1" },
    "auth":         { "scheme": "bearer", "token": "..." },
    "resume": {
      "session_id":     "sess_01JABCDEFGHJKMNPQ",
      "resume_token":   "rt_4f8c...",
      "last_event_seq": 1827
    }
  }
}
```

On successful resume the runtime:

1. Replays all `job.event`, `job.result`, and `job.error` messages with
   `event_seq > 1827` that are still within the buffer window.
2. Issues a new `session.welcome` reusing the original `session_id`
   and a fresh `resume_token`.
3. Resumes live streaming of events.

If `last_event_seq` is older than the buffer window, the runtime MUST
respond with `session.error` containing
`{"code": "RESUME_WINDOW_EXPIRED"}` and close the transport. The
client MAY then resubmit jobs using their original `idempotency_key`
to recover (Section 7.2).

### 6.4. Close

Either party MAY initiate clean session closure with `session.bye`:

```json
{ "type": "session.bye", "payload": { "reason": "client_shutdown" } }
```

After `session.bye`, no further ARCP messages MUST be sent on the
transport. The runtime MAY retain session state for the buffer window
to permit resume.

---

## 7. Jobs

### 7.1. Submission and Acceptance

**Client → Runtime:**

```json
{
  "type": "job.submit",
  "session_id": "sess_...",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "payload": {
    "agent": "code-refactor",
    "input": {
      "instruction": "Migrate the auth module from callbacks to async/await.",
      "repo_path":   "/workspace/myapp"
    },
    "lease_request": {
      "fs.read":  ["/workspace/myapp/**"],
      "fs.write": ["/workspace/myapp/src/auth/**"],
      "agent.delegate": ["test-runner"]
    },
    "idempotency_key": "refactor-auth-2026-05-13-a",
    "max_runtime_sec": 1800
  }
}
```

**Runtime → Client:**

```json
{
  "type": "job.accepted",
  "session_id": "sess_...",
  "payload": {
    "job_id": "job_01JABC...",
    "lease":  { /* effective lease, may equal lease_request or be a subset */ },
    "accepted_at": "2026-05-13T19:42:00Z"
  }
}
```

The runtime MAY reduce the requested lease (e.g., because the bearer
token's authorization caps it) but MUST NOT silently expand it.
The effective lease appears in `job.accepted.payload.lease`.

### 7.2. Idempotency

Two levels of idempotency apply:

- **Transport-level**: the `id` field on each envelope. Used by
  transports that may deliver duplicates.
- **Logical**: the `idempotency_key` field in `job.submit.payload`.
  Two `job.submit` messages with the same `(session.auth.principal,
  idempotency_key)` within an implementation-defined window (default
  24 hours) MUST resolve to the same `job_id`. If the prior job is
  still running, the runtime MUST return the existing `job_id` and
  begin streaming current events. If terminal, the runtime MUST
  return the existing `job_id` and replay the terminal event.

Submitting a job with an `idempotency_key` that matches a prior job
but with a *different* `agent` or materially different `input` MUST
result in error `DUPLICATE_KEY`.

### 7.3. Lifecycle

A job's status transitions are:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/job-lifecycle-dark.svg">
  <img alt="ARCP job lifecycle FSM — pending → running → {success | error | cancelled | timed_out}" src="diagrams/job-lifecycle-light.svg">
</picture>

The terminal events `job.result` (success) and `job.error`
(failure/cancelled/timed_out) carry a `final_status` field
distinguishing the terminal state.

### 7.4. Cancellation

The client MAY cancel a running job:

```json
{
  "type": "job.cancel",
  "session_id": "sess_...",
  "job_id": "job_01JABC...",
  "payload": { "reason": "User requested cancel" }
}
```

Cancellation is cooperative. The runtime MUST signal the agent to
stop, MUST emit a `job.error` with `final_status: "cancelled"`
within a bounded grace period (default 30 seconds), and MUST release
the job's lease.

If the agent does not honor cancellation within the grace period, the
runtime MAY forcibly terminate the agent process. Whether and how it
does so is a runtime implementation concern.

---

## 8. Job Events

### 8.1. Event Envelope

Job events flow runtime → client during job execution:

```json
{
  "arcp": "1",
  "id": "01J...",
  "type": "job.event",
  "session_id": "sess_...",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "job_id": "job_01JABC...",
  "event_seq": 1827,
  "payload": {
    "kind": "<event kind>",
    "ts":   "2026-05-13T19:42:13.842Z",
    "body": { /* kind-specific */ }
  }
}
```

### 8.2. Event Kinds

The following event `kind` values are reserved in v1.0:

- `log` — Free-form log message. `body: { level, message }`.
- `thought` — Agent-internal reasoning trace. `body: { text }`.
- `tool_call` — Agent invoked a tool. `body: { tool, args, call_id }`.
- `tool_result` — Tool returned. `body: { call_id, result | error }`.
- `status` — Lifecycle marker. `body: { phase, message }`.
- `metric` — Numeric measurement. `body: { name, value, unit }`.
- `artifact_ref` — Agent produced an addressable artifact.
  `body: { uri, content_type, byte_size?, sha256? }`.
- `delegate` — Agent requested sub-job creation. See Section 10.

Implementations MAY define additional event kinds in a vendor
namespace (`x-vendor.kind`). Receivers MUST ignore unknown kinds
rather than erroring.

### 8.3. Ordering and Sequence Numbers

Event sequence numbers are:

- **Session-scoped**: All `job.event`, `job.result`, and `job.error`
  messages within a session share one monotonically increasing seq
  space, even across multiple concurrent jobs. This allows a single
  resume operation to recover all jobs at once.
- **Strictly monotonic**: `event_seq[n+1] > event_seq[n]` for any two
  consecutive messages from the runtime within a session.
- **Gap-free across reconnects**: Resume MUST replay every event
  whose seq is greater than the client's `last_event_seq`.

Per-job ordering is implied: events for a given `job_id` MUST appear
in the order they were produced.

---

## 9. Leases

### 9.1. Capability Model

A lease is the complete, immutable authority granted to a job at
submission. It is a JSON object mapping capability names to lists of
pattern constraints:

```json
{
  "fs.read":        ["/workspace/myapp/**"],
  "fs.write":       ["/workspace/myapp/src/auth/**"],
  "net.fetch":      ["https://api.example.com/**"],
  "tool.call":      ["mcp:github/*", "humanq.*"],
  "agent.delegate": ["test-runner", "lint-runner"]
}
```

A job MAY perform an operation if and only if its lease contains the
relevant capability and at least one pattern matches the operation's
target.

### 9.2. Lease Grammar

Capability names use dot-namespaced lowercase identifiers. Reserved
top-level namespaces in v1.0:

| Namespace        | Semantics                                     |
|------------------|-----------------------------------------------|
| `fs.read`        | Filesystem read; patterns are path globs.     |
| `fs.write`       | Filesystem write; patterns are path globs.    |
| `net.fetch`      | Outbound HTTP/HTTPS; patterns are URL globs.  |
| `tool.call`      | Calling registered tools; patterns are tool name globs. |
| `agent.delegate` | Delegating to sub-agents; patterns are agent name globs. |

Patterns use glob syntax with `*` matching any single path or name
segment and `**` matching zero or more segments. Implementations MUST
treat patterns as anchored (no partial-string matching).

### 9.3. Enforcement

The runtime is the trust boundary. It MUST validate every operation
attempted by an agent against the lease before allowing it to proceed.
Operations failing lease checks MUST result in `PERMISSION_DENIED` and
MUST NOT silently degrade or partial-apply.

Lease checks MUST be performed even when the agent runs in a sandbox
that nominally enforces the same constraints. The protocol-level
check is the ground truth.

### 9.4. Lease Subsetting

Lease `B` is a subset of lease `A` if and only if, for every
capability `c` in `B`, every pattern in `B[c]` is matched by at least
one pattern in `A[c]`. Capabilities not present in `B` are trivially
subset-conforming.

A pattern `p2` is matched by pattern `p1` if every string that
matches `p2` also matches `p1`. Implementations MUST validate this
relation conservatively: if subset cannot be proven, the delegation
MUST be rejected.

---

## 10. Delegation

### 10.1. Delegate Event

A running job initiates delegation by emitting a `job.event` with
kind `delegate`:

```json
{
  "type": "job.event",
  "session_id": "sess_...",
  "job_id": "job_01JABC...",
  "event_seq": 1830,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "payload": {
    "kind": "delegate",
    "ts":   "2026-05-13T19:43:00Z",
    "body": {
      "delegate_id":   "del_01JX...",
      "agent":         "test-runner",
      "input":         { "suite": "auth", "paths": ["/workspace/myapp/tests/auth/**"] },
      "lease_request": {
        "fs.read":   ["/workspace/myapp/**"],
        "fs.write":  ["/workspace/myapp/test-output/**"]
      }
    }
  }
}
```

The runtime responds within the same session by creating a new job
and emitting a `job.accepted` carrying both the new `job_id` and a
back-reference:

```json
{
  "type": "job.accepted",
  "session_id": "sess_...",
  "payload": {
    "job_id": "job_01JDEF...",
    "parent_job_id": "job_01JABC...",
    "delegate_id":   "del_01JX...",
    "lease":         { /* effective subset lease */ }
  }
}
```

### 10.2. Subset Validation

The runtime MUST validate that the requested child lease is a subset
of the parent's effective lease (Section 9.4). Failed validation MUST
produce error `LEASE_SUBSET_VIOLATION` *as a `tool_result` event on the
parent job*, not as a session-level error. The parent agent receives
the failure and decides how to proceed.

### 10.3. Trace Context Propagation

Delegated jobs MUST inherit the parent's `trace_id`. The runtime
SHOULD create a new span (with a fresh `span_id`) for the child job
and propagate W3C `tracestate` if present.

This is what makes a multi-agent workload visible as a single trace
tree in observability tooling.

---

## 11. Trace Propagation

ARCP uses W3C Trace Context [TRACE-CONTEXT]:

- The `trace_id` envelope field carries the 16-byte trace identifier
  encoded as 32 lowercase hex characters.
- Clients submitting `job.submit` SHOULD include the active `trace_id`
  from their calling context. If absent, the runtime MUST generate
  one and include it in `job.accepted.payload.trace_id`.
- The runtime SHOULD emit OpenTelemetry spans for session lifecycle,
  job lifecycle, and significant events. Span attributes SHOULD
  include `arcp.session_id`, `arcp.job_id`, `arcp.agent`,
  `arcp.lease.capabilities`.

---

## 12. Error Taxonomy

ARCP defines a closed set of canonical error codes for v1.0:

| Code                       | Meaning                                                    |
|----------------------------|------------------------------------------------------------|
| `PERMISSION_DENIED`        | Operation rejected by lease enforcement.                   |
| `LEASE_SUBSET_VIOLATION`   | Delegation request expanded beyond parent lease.           |
| `JOB_NOT_FOUND`            | Referenced `job_id` does not exist in this session.        |
| `DUPLICATE_KEY`            | `idempotency_key` reuse with conflicting parameters.       |
| `AGENT_NOT_AVAILABLE`      | Requested `agent` is not registered with the runtime.      |
| `CANCELLED`                | Job ended due to client cancellation.                      |
| `TIMEOUT`                  | Job exceeded `max_runtime_sec`.                            |
| `RESUME_WINDOW_EXPIRED`    | Resume attempted after the buffer window closed.           |
| `HEARTBEAT_LOST`           | Runtime detected client disconnection without close.       |
| `INVALID_REQUEST`          | Malformed envelope or payload schema violation.            |
| `UNAUTHENTICATED`          | Missing or invalid authentication on `session.hello`.      |
| `INTERNAL_ERROR`           | Unrecoverable runtime fault. Always retryable.             |

Error payload shape:

```json
{
  "code":      "PERMISSION_DENIED",
  "message":   "Write to /etc/passwd denied by lease.",
  "retryable": false,
  "details":   { /* optional, error-specific */ }
}
```

The `retryable` boolean signals whether a naive retry might succeed.
Clients SHOULD respect it. Agent-level errors (the agent reports a
business failure) appear inside `tool_result` events or `job.error`
payloads with vendor-specific codes; only the codes above are
protocol-canonical.

---

## 13. Examples

The following examples illustrate complete flows. Envelopes are
abbreviated to focus on relevant fields.

### 13.1. Simple Job

A client submits a one-shot data-analysis job and receives results.

```
C → R:  session.hello
R → C:  session.welcome (session_id=sess_A1, resume_token=rt_X1)

C → R:  job.submit { agent: "data-analyzer",
                    input: { dataset: "s3://example/sales.csv" },
                    lease_request: { net.fetch: ["s3://example/**"] },
                    idempotency_key: "sales-q1-analysis" }
R → C:  job.accepted { job_id: job_J1, lease: { net.fetch: [...] } }

R → C:  job.event[seq=1] { kind: status, body: { phase: "fetching" } }
R → C:  job.event[seq=2] { kind: log,    body: { level: info, message: "12,408 rows loaded" } }
R → C:  job.event[seq=3] { kind: thought, body: { text: "Outlier in column 'revenue' row 4421" } }
R → C:  job.event[seq=4] { kind: metric, body: { name: "rows", value: 12408 } }
R → C:  job.event[seq=5] { kind: artifact_ref,
                          body: { uri: "arcp://artifacts/sess_A1/J1/report.html",
                                  content_type: "text/html",
                                  byte_size: 38291 } }
R → C:  job.result[seq=6] { final_status: "success",
                           summary: "Analysis complete. 3 outliers, $42K total." }
```

### 13.2. Delegation

A code-refactor job delegates test execution after applying changes.

```
C → R:  session.hello
R → C:  session.welcome

C → R:  job.submit { agent: "code-refactor",
                    lease_request: {
                      fs.read:  ["/workspace/myapp/**"],
                      fs.write: ["/workspace/myapp/src/auth/**"],
                      agent.delegate: ["test-runner"] } }
R → C:  job.accepted { job_id: job_PARENT }

R → C:  job.event[seq=10] { kind: status,    body: { phase: "analyzing" } }
R → C:  job.event[seq=11] { kind: tool_call, body: { tool: "fs.read", args: ... } }
R → C:  job.event[seq=12] { kind: tool_call, body: { tool: "fs.write", args: ... } }

R → C:  job.event[seq=13] { kind: delegate,
                            body: { delegate_id: del_T1,
                                    agent: "test-runner",
                                    input: { suite: "auth" },
                                    lease_request: {
                                      fs.read:  ["/workspace/myapp/**"],
                                      fs.write: ["/workspace/myapp/test-output/**"] } } }
R → C:  job.accepted { job_id: job_CHILD, parent_job_id: job_PARENT, delegate_id: del_T1 }

R → C:  job.event[seq=14] { job_id: job_CHILD, kind: status,  body: { phase: "running" } }
R → C:  job.event[seq=15] { job_id: job_CHILD, kind: log,     body: { level: info, message: "127/127 passed" } }
R → C:  job.result[seq=16] { job_id: job_CHILD, final_status: "success" }

R → C:  job.event[seq=17] { job_id: job_PARENT, kind: status, body: { phase: "completing" } }
R → C:  job.result[seq=18] { job_id: job_PARENT, final_status: "success" }
```

Note that events from both parent and child are interleaved in the
session's seq space, ordered by emission time. Per-job ordering is
preserved (events for `job_CHILD` are monotonic within `job_CHILD`).

### 13.3. Resume After Reconnect

A long-running job's transport drops mid-stream; the client recovers.

```
C → R:  session.hello
R → C:  session.welcome (session_id=sess_A1, resume_token=rt_X1, resume_window_sec=600)

C → R:  job.submit { agent: "web-research", input: { topic: "..." } }
R → C:  job.accepted { job_id: job_R1 }

R → C:  job.event[seq=1..40]   (... 40 events arrive over 4 minutes ...)

*** transport drops at seq=40 ***
*** client persisted last_event_seq=40, session_id=sess_A1, resume_token=rt_X1 ***

(... 90 seconds later, client reconnects ...)

C → R:  session.hello { resume: { session_id: sess_A1,
                                   resume_token: rt_X1,
                                   last_event_seq: 40 } }
R → C:  session.welcome (session_id=sess_A1, resume_token=rt_X2)
R → C:  job.event[seq=41..47]  (replayed from server buffer)
R → C:  job.event[seq=48..]    (live)
...
R → C:  job.result[seq=72] { final_status: "success" }
```

If the client had reconnected after the 600-second window:

```
C → R:  session.hello { resume: { ..., last_event_seq: 40 } }
R → C:  session.error { code: "RESUME_WINDOW_EXPIRED" }
*** transport closed ***
```

The client MAY then start a fresh session and resubmit the job with
the same `idempotency_key`. If the runtime is still running the
original job, the resubmit returns the same `job_id` and live events
resume from the current seq.

### 13.4. Lease Violation

An agent attempts to read a file outside its lease.

```
C → R:  job.submit { agent: "code-refactor",
                    lease_request: {
                      fs.read:  ["/workspace/myapp/src/**"],
                      fs.write: ["/workspace/myapp/src/**"] } }
R → C:  job.accepted { job_id: job_LV }

R → C:  job.event[seq=1] { kind: tool_call,
                          body: { tool: "fs.read", call_id: c1,
                                  args: { path: "/etc/passwd" } } }
R → C:  job.event[seq=2] { kind: tool_result,
                          body: { call_id: c1,
                                  error: { code: "PERMISSION_DENIED",
                                           message: "Read of /etc/passwd denied by lease",
                                           retryable: false } } }
R → C:  job.event[seq=3] { kind: log,
                          body: { level: warn, message: "Skipping unauthorized read" } }
...
```

The agent receives the error inside the `tool_result`, decides how to
proceed (in this case, logging and continuing), and the job continues.
Lease violations are *not* session-fatal; they're routine error
handling for an agent.

### 13.5. Idempotent Retry

A client's first submit times out; it retries with the same key.

```
C → R:  job.submit { idempotency_key: "weekly-report-2026-W19", agent: ... }
*** transport drops before job.accepted arrives ***

(... client reconnects, resumes session ...)
*** during resume replay, client did not see a job.accepted for this submit ***

C → R:  job.submit { idempotency_key: "weekly-report-2026-W19", agent: ... }
R → C:  job.accepted { job_id: job_W19 }       *** existing, server-side, still running ***
R → C:  job.event[seq=N..]                     *** live events continue ***
```

The runtime detected the duplicate `idempotency_key`, recognized the
existing in-flight job, and returned its `job_id` rather than starting
a second one. The client transparently picks up where the first
submit left off.

If the agent had been a different one or the input had differed
materially:

```
C → R:  job.submit { idempotency_key: "weekly-report-2026-W19",
                    agent: "different-agent", ... }
R → C:  session.error { code: "DUPLICATE_KEY",
                       message: "Key matches existing job_W19 with different agent",
                       retryable: false }
```

---

## 14. Security Considerations

**Transport security.** Network deployments MUST use TLS [RFC8446].
Bearer tokens MUST NOT be transmitted over unencrypted transports.
The `wss://` scheme is REQUIRED for WebSocket transport in network
deployments.

**Resume token treatment.** The `resume_token` is a session credential.
Disclosure permits an attacker to hijack a session in progress.
Clients MUST store it with at least the protection afforded the
original bearer token. Runtimes MUST generate `resume_token` values
with at least 128 bits of cryptographically random entropy.

**Lease as the trust boundary.** Runtimes MUST enforce leases before
allowing operations. Defense-in-depth via sandboxing is encouraged but
does not relieve the runtime of protocol-level enforcement.

**Pattern matching subtleties.** Glob pattern matching is a known
source of authority-bypass bugs (e.g., `..` traversal, symlink
resolution, encoded characters). Runtimes MUST canonicalize paths and
URLs before lease evaluation. Implementations are strongly advised to
unit-test pattern matching against known attack patterns.

**Trace context as a side channel.** `trace_id` and `tracestate`
fields are propagated end-to-end and may be logged by intermediaries.
Implementations MUST NOT place secrets in trace context. Span
attributes likewise MUST NOT contain secrets, credentials, or PII
without explicit user opt-in.

**Buffered events on the runtime.** The resume buffer retains
potentially sensitive event payloads (tool inputs/outputs, logs).
Runtimes MUST encrypt buffered events at rest if the deployment
environment is untrusted, and MUST purge them when the buffer window
expires.

**Denial of service.** Long resume windows and unbounded event
buffers expose runtimes to memory exhaustion. Runtimes SHOULD enforce
per-session caps on (a) buffered event count, (b) buffered event byte
total, and (c) concurrent jobs. Exceeding limits MUST surface as
`INTERNAL_ERROR` with a non-retryable signal, not silent truncation.

**Agent-level threats are out of scope.** This document does not
address prompt injection, adversarial tool outputs, or malicious
agent behavior. Those concerns lie within the agent and its tool
configuration, not the transport.

---

## 15. IANA Considerations

This document defines no IANA-registered values in its v1.0 draft.
A future revision proposed for adoption will register:

- URI scheme `arcp://` for artifact references.
- An IANA registry for top-level capability namespaces (Section 9.2).
- An IANA registry for canonical event `kind` values (Section 8.2).
- An IANA registry for canonical error codes (Section 12).

Pending adoption, implementations SHOULD restrict additions to the
`x-vendor` prefix to minimize collision risk with future registered
values.

---

## 16. References

### 16.1. Normative

- [RFC2119] Bradner, S., "Key words for use in RFCs to Indicate
  Requirement Levels", BCP 14, RFC 2119, March 1997.
- [RFC6455] Fette, I., and A. Melnikov, "The WebSocket Protocol",
  RFC 6455, December 2011.
- [RFC8174] Leiba, B., "Ambiguity of Uppercase vs Lowercase in
  RFC 2119 Key Words", BCP 14, RFC 8174, May 2017.
- [RFC8259] Bray, T., "The JavaScript Object Notation (JSON) Data
  Interchange Format", STD 90, RFC 8259, December 2017.
- [RFC8446] Rescorla, E., "The Transport Layer Security (TLS)
  Protocol Version 1.3", RFC 8446, August 2018.
- [TRACE-CONTEXT] W3C, "Trace Context", W3C Recommendation,
  November 2021.

### 16.2. Informative

- Model Context Protocol (MCP): https://modelcontextprotocol.io/
- OpenTelemetry: https://opentelemetry.io/

---

## Authors' Addresses

```
[Author Name]
Email: [email@example.com]
```

---

*End of draft specification.*
