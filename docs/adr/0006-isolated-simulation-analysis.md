# ADR 0006 — Credential-free analysis and fenced simulation results

Date: 2026-11-12 (Asia/Rangoon). Status: implemented for M06 review.
Base: accepted M05 `0edbdedd1d875105636f866cb3af86c039f35932`.

A native model parser must not inherit API/database/Telegram privileges. Keep a
modular monolith with a separately launched trusted host orchestrator; each model
runs in a fresh restricted Docker container containing only Python, bounded
geometry code and pinned PrusaSlicer. No queue service, physical printer records,
pricing, payments or public worker administration are introduced.

Add Alembic `0005_isolated_slicing` after immutable 0001–0004. Add only virtual
models, approved versioned slicer profiles, model analyses and slicing runs, plus
lease/retry/result fields on M04 tasks. Optional dimension confirmations extend
print items; absent dimensions are omitted from canonicalization, preserving all
old hashes/snapshots. Requests may move submitted -> analyzing only after actual
startup, and to manual_review when terminal. Design-stage state remains independent.

Use PostgreSQL locks, expiring UUID fences, bounded retry budgets and immutable
attempt results. A current task result pointer plus matching revision/spec/file
checks determine authority. Reruns retain earlier records but remove current
authority until a new result is committed. The publication transaction includes
audit/outbox writes; a failed commit produces no partial authoritative result.
System events use a checked system actor rather than falsely attributing worker
execution to the customer. Existing user audit records keep their identity.

Raw 3MF never enters the slicer. Normalize permitted geometry in the sandbox and
apply only allowlisted trusted numeric profiles with empty hooks. Inspect the real
pinned CLI, detect its implicit repairs, and refuse geometry-changing repair.
Discard private G-code after validating positive grams/time and recording exact
and timestamp-normalized hashes. Simulation-only and uncalibrated checks are in
SQL and API, in addition to disabled live feature flags.

Local tests exercise the real sandbox. Cloud cgroup delegation does not establish
requested aggregate CPU/RAM/PID enforcement; verified POSIX process budgets and
bounded tmpfs remain explicit evidence with that limitation. Target-host cgroup
verification and preferably a VM/microVM boundary are release prerequisites for
public hostile workloads. No production isolation claim or deployment is made.

Operations/recovery: [WORKER_OPERATIONS.md](../WORKER_OPERATIONS.md).
Profile assumptions and precision: [SLICER_PROFILES.md](../SLICER_PROFILES.md).
