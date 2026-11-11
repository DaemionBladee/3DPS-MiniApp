# ADR 0003 — M03 business transactions and initial stage drafts

Date: 2026-11-11. Status: implemented for M03 review. Extends ADRs 0001/0002;
no approval of live commerce or deployment is implied.

## Context

M02 already owns users, sessions, Telegram verification, cookie/CSRF/Origin
security and Alembic revision `0001_auth_foundation`. M03 must establish useful
business records and shared transaction primitives without inventing M04–M12.
The full target data model includes fields and tables whose guards do not exist.

## Decision

- Add only `service_projects`, `service_requests`, `audit_logs`,
  `idempotency_records` and `notification_outbox` in `0002_business_foundation`.
  Keep the existing auth revision unchanged. UUIDs and UTC dates are DB generated.
- A project is immutable through this API. Its first request is `printing` for
  printing-only and `design` for custom-design/combined projects. Composite FK
  enforces matching parent, customer, service selection and simulation mode;
  unique project/stage prevents duplicate initial stages. Only simulation rows
  are legal. There is no mode conversion API.
- Do not invent a project status aggregation rule: the target `project.status`
  is deferred until a real multi-stage lifecycle exists. Requests expose only
  `draft` and terminal `cancelled` now. Draft notes are a skeleton, not a design
  scope or validated print specification. `revision` changes with notes;
  `version` changes with every mutation; hash binds service, stage and notes.
- Submission fails closed (`409 intake_not_available`) until M04 file/item
  validation and M05 design scope guards exist. No fake successful submission,
  analysis task, design version, payable order or print-stage derivation.
- Customers create/edit their own drafts and cancel with a reason. Owner may
  inspect/cancel customer drafts with a reason, but cannot edit their notes or
  choose another customer's identity on creation. Inaccessible IDs return 404.
- Commands run in a unit of work. An actor/action/key advisory transaction lock
  serializes retries across processes. Persist canonical payload SHA-256 and the
  typed original response under a composite primary key. A different payload
  conflicts; an exact retry returns the original response without a new event.
  Recheck resource access before replay, including Owner allowlist removal.
- Revalidate and lock the actor and session inside the command transaction.
  Use user `FOR NO KEY UPDATE`, then session `FOR UPDATE`, matching login's
  user-before-session order. Non-key user updates/revocation serialize without
  blocking foreign-key key-share locks from another actor's command. Lock the
  request and compare expected version before mutation; racing versions yield
  one winner and 409 for the stale command.
- Write mutation, audit, pending outbox event and successful idempotency result
  in one transaction. Any failure rolls all of them back. Audit snapshots carry
  IDs, old/new status, hash, mode and versions; notes are not copied to events.
  PostgreSQL rejects audit UPDATE/DELETE. DB owners/superusers remain trusted;
  this is not tamper-proof protection against an administrator or TRUNCATE.
- The initial audit entity is FK-bound to a request, and actors are authenticated
  users. Future system/other-domain auditing must extend this schema explicitly.
  Outbox has a unique event key and one row per audit event, with a customer
  recipient and minimized payload. These are durable foundation events, not
  delivered alerts. M08 adds approved notification routing/delivery; M13 adds
  retry/dead-letter/reporting. No worker or Telegram network call is added.
- List APIs use bounded `limit`/`offset` (1–100 / 0–10000), deterministic
  created-at/UUID ordering, and `next_offset`. Customer+time and global request
  time indexes support the initial views. Future cursor/filter contracts must
  be explicit; offset pages are not snapshots during concurrent insertions.
- React uses generated OpenAPI schemas and the existing relative same-origin
  client. Authenticated users explicitly open/load drafts. Failed command keys
  stay in component memory for retries; ambiguous transport failures disable
  further edits until retry. No long-lived token or business cache in storage.

## Consequences and recovery

M04 extends intake and enables only properly validated submission. M05 extends
stage constraints and adds exact approved-design lineage before creating the
single derived print request. Later fields/tables require new migrations.
There is no automatic pruning of audit, idempotency or outbox records; retention
and application DB-role hardening need explicit policy/release work. Never
prune M02 launch-proof uniqueness as part of business cleanup.

Migration downgrade removes business history; it is tested only in a disposable
fixture. Real recovery requires a reviewed backup/restore or forward migration.
No migration was run against development customer data or production data.
