# ADR 0004 — Private, versioned printing intake

Date: 2026-11-11 (Asia/Rangoon). Status: implemented for M04 review.
Accepted starting commit: `3ae6f5c94d9ebbefce2c863c1968a9734ff51078` (M03).

## Context

M03 already owns parent projects/requests, server-derived ownership, locking,
idempotency, audit and outbox. M04 must allow real persistence of untrusted model
files and specifications without claiming that M06 analysis or commercial
fulfillment exists. Filesystem writes cannot share a PostgreSQL transaction.

## Decisions

1. Extend the single migration chain with `0003_printing_intake`; preserve 0001
   and 0002. Add only items, uploaded-file reservations and processing tasks.
   Composite FKs bind each item/file/task to the same printing request/customer;
   the current-model FK also binds the exact item. Parent project/stage rules
   remain intact. Existing hashes retain schema version 1 until a meaningful edit.
2. Reserve a durable file row before writing bytes. Lock principal/session,
   request and a short global quota advisory lock while checking counted bytes
   and file counts. Receiving and delete-pending reservations consume quota.
   Release database locks before streaming/validation. Default global inflight
   cap is two; it bounds concurrent parsers across API processes sharing the DB.
3. Store opaque random keys in private incoming/quarantine/ready directories.
   Stream with bounded writes and size/SHA-256 checks. The parser runs in isolated
   Python mode with a cleared environment, closed inherited descriptors, CPU,
   address-space, descriptor, file-size and wall-time limits. It reads only
   trusted stdlib validation code; models are data, never executed or sliced.
   This is resource isolation, **not** a separate UID/network/mount sandbox.
4. Accept structural binary/ASCII STL, mesh OBJ without material/texture/file
   references, and a conservative single-Core-model-part 3MF profile. Bound ZIP
   entries, expansion, per-entry size, ratio, XML depth and object references;
   reject traversal, symlinks, duplicate paths, nested/foreign parts, external
   relationships, DTD/entities and unsupported extensions. No archive extraction
   or network resource fetch occurs. Structural validity is not manufacturability.
5. Recheck current session, request version and upload lease before promotion.
   File attachment, revised spec/hash, audit, outbox and command result commit
   atomically. Promote the blob before commit; a pre-existing reservation tracks
   a crash. After ambiguous commit, compensation checks committed state and
   never deletes a ready attachment. Cleanup fences by lease token/key/state;
   it releases quota only after actual unlink. No blind ready-blob pruning.
6. Canonical schema v2 includes stage/service, notes, fulfillment, sorted active
   items/specifications and exact file IDs/SHA/format/size. Meaningful edits
   advance revision and version; no-op settings do not. File upload provenance
   retains its original revision; current items and tasks bind the current exact
   spec. New revisions supersede older pending task references. Future approval
   tables do not exist and are not fabricated.
7. Validated `/submit` freezes the current spec/revision/hash and creates one
   unique pending model-analysis task per current model in the same transaction
   as status, audit, outbox and idempotency result. Request stays `submitted`;
   queued task existence never changes it to `analyzing`. No worker is launched.
   SQL triggers freeze submitted specs/items and validated-file provenance.
8. Keep M03 generic transitions separate: cancellation of drafts still works;
   its generic submission path remains guarded. Only printing-stage `/submit`
   with complete item/file validation succeeds. No submitted-request reopening
   policy is invented: later clarification requires an explicit successor design.
9. Reuse verified sessions, CSRF, exact Origin, server-only Owner configuration,
   current-resource authorization and transaction primitives. Customer edits own
   draft; Owner inspects/downloads without impersonating Customer edits. Separate
   DB-backed business/upload/download rate namespaces preserve auth rate buckets.
10. React serializes commands and autosaves to the API with expected versions.
    Ambiguous/stale command failures pause subsequent mutations until exact retry
    or explicit reload. Retry keys and selected File objects live only in memory;
    reload recovers committed server data and requires reselecting unfinished
    uploads. Catalog options are explicitly development-only, with uncertainty
    choices for Owner review. They do not claim real inventory or capability.

## Consequences and recovery

The migration upgrades seeded M03 history without data loss. Empty intake
schemas can downgrade to 0002 and re-upgrade; populated intake downgrade refuses
rather than discarding models/submissions. Production recovery requires reviewed
forward migration or tested database **and private-volume** restore.

Ready uploads (including cancelled drafts) are retained and charged. Retention,
delete rights, encrypted object storage, backup/restore and cleanup scheduling
require reviewed operational policies. The local adapter supports one shared
private volume; multiple independent API filesystems are unsupported. A future
object-store adapter must preserve opaque keys, checksum verification, authorized
reads and commit/compensation semantics.

M06 must supply stronger OS isolation without credentials or network access,
exact file/revision/hash provenance, task claiming/retries and worker execution
states. M05 extends design lineage and reference-file roles through new migrations;
this mesh-only intake API does not grant design/digital-delivery rights. No live
feature flag, quotation, payment, printer assignment or production control changes.
