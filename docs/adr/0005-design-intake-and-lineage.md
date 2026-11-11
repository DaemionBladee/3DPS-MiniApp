# ADR 0005 — Design intake, exact proofs and combined-stage lineage

Date: 2026-11-11 (Asia/Rangoon). Status: implemented for M05 review.
Accepted starting point: M04 `de9ad298806831289bf60f727bb4cc06bb432fe1`.

## Context

Design-only requests need briefs and scope without printing prerequisites.
Combined projects need independent stages and a traceable, approved manufacturing
version. Scope agreement, proof approval, paid work and delivery are distinct
permissions. M05 must not invent M08 quotations, M09 funds or M12 delivery.

## Decisions

- Add `0004_design_intake` after immutable revisions 0001–0003. Create only
  `design_projects`, `design_scopes`, `design_versions`, `design_reviews`. Extend
  uploaded files with purpose/uploader and nullable item for design attachments;
  add a direct customer/request FK and a purpose/item check. Extend stage requests
  with `source_design_version_id`, composite lineage FK and source uniqueness.
- New design-stage requests receive an empty persisted design project in their
  creation transaction. Existing M03/M04 drafts retain their original data/hashes;
  an explicit authenticated initialize command opens the design editor. Reads
  never create domain records. Brief/spec schema v3 binds complete brief, notes
  and exact current reference IDs/hashes. Customer edits and references advance
  request revision/version; submission freezes the snapshot with zero print items.
- Scope proposals are Owner-authored, versioned and immutable in content.
  Customer agreement names only the latest proposal and records actor/time;
  previous agreements remain historical. A changed scope clears current fixture
  and proof approval; old proofs/reviews stay immutable. These agreements are
  **simulation agreements, not issued contractual quotations** (`binding=false`).
- Require an Owner action explicitly confirming a simulation quote-and-paid
  fixture for the exact agreed scope before proof work. `fixture_scope_id` is
  separate from any financial record; it creates no amount, credit, order,
  obligation or real paid status. All rows stay simulation-only. M08/M09 must
  later supply actual quote/payment guards; the fixture is never live evidence.
- M05 enables draft -> brief_received -> scoping -> awaiting_payment, then
  fixture -> designing -> customer_review -> approved. A changes-requested
  review returns to designing; it does not overwrite the reviewed version.
  `quoted`, live work and delivery transitions remain deferred. This is the
  explicitly permitted simulation fixture path, not a claim that real payments
  exist. Manufacturing-only projects remain `approved`; M00-D07's terminal
  handoff/delivery semantics stay open for M12.
- Published proofs bind immutable version number, scope, brief hash, exact
  preview/model SHA and publisher. SQL guards validate file/project/purpose
  relationships and reject updates/deletes of versions/reviews. A customer
  terminal review names the latest version and current scope under locks;
  one review per version, expected versions and idempotency serialize races.
  Publishing a later version clears approval; previous reviews grant it nothing.
  Revision limits count subsequent published proofs per scope, capped histories
  prevent unbounded expansion. There is no interactive CAD/model renderer.
- Reuse M04 durable reservations, quota/rate checks, private quarantine, checksum
  streaming, compensation and lease-fenced cleanup. Model-key fingerprints remain
  byte-compatible with M04 and cached DTO defaults preserve old upload retries.
  References/proof previews allow PNG, JPEG and plain UTF-8 TXT. Pillow 13.0.0
  is pinned for bounded image verification/full decoding; malformed/truncated,
  animated or oversized images and unsafe/unsupported documents fail closed.
  PDF, SVG, Office, HTML/RTF and archive reference uploads are unsupported.
- Distinguish `design_reference`, `design_proof`, `design_manufacturing` and
  `model`. Customers access own references and only published review previews;
  unpublished proofs and manufacturing source stay Owner-only. Review previews
  are authenticated byte fetches rendered as images or escaped text. No
  `design_deliveries` table or source release is added, even when future rights
  are included in scope. Scope rights alone do not satisfy M12 delivery gates.
- Owner conversion creates at most one printing draft under the existing parent
  and references the exact currently approved manufacturing-ready version. DB
  checks/FKs, the existing unique project/stage constraint, row locks and command
  idempotency protect the relationship. Conversion freezes further scope/proof
  replacement in this M05 slice; later revision/replacement needs reviewed policy.
- The derived draft starts with one empty print item, with no invented stock,
  quality or paid status. A separate Owner action streams the approved model
  through the M04 upload transaction into private print storage. Copies are
  quota-charged and retain their provenance; Customer downloads remain denied.
  Printing submission requires complete actual specs and bytes matching the
  approved manufacturing SHA. Design state/fixture never submits, pays for or
  starts the printing stage. Tasks remain pending; M06 is not implemented.
- All mutations revalidate sessions, current roles/resources, versions, CSRF and
  Origin; audit/outbox/result share one transaction. Audit metadata binds exact
  design/scope/version/file/linked-request IDs without copying briefs into events.
  UI autosaves backend drafts; failed commands keep exact keys in memory and
  require retry/reload. No private browser localStorage persistence is introduced.

## Recovery and remaining boundaries

Seeded M04 users/sessions/model/request relationships survive upgrade. With no
M05 data, downgrade/re-upgrade preserves M04 models; with M05 records it refuses
rather than dropping history. Reviewed forward migration or tested database plus
private-volume restore is the recovery path for retained environments.

Validation subprocesses clear inherited environment/descriptors and have CPU,
memory, file-size and wall-time bounds. They share the API container's OS
namespaces; stronger isolation remains necessary before public intake/M06.
Private-volume sharing, encryption, retention/deletion and backup/restore need
operational review. Real Telegram clients and intended HTTPS gateway remain
external tests. No live business flag, Operator, slicer, printer operation,
quotation, payment or digital deliverable release is introduced.
