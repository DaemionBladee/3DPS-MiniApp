# M00 implementation baseline — v1.4

Audit date: 2026-11-11 (Asia/Rangoon). Status: **M00 baseline reviewed and approved by the owner in the M01 start instruction.**
The inventory and checks below are the historical M00 snapshot, not the current
implementation status. The owner subsequently reviewed M01 and authorized M02;
see the M02 report for the implemented auth foundation. This baseline does not
authorize M03 or live operation. Remaining policy/schema
decisions retain their documented deadlines. No release gate has passed.

## 1. Evidence and requirements provenance

The actual checkout is `/workspace/3DPS-MiniApp`, branch `work`, at
`3a6da2d6df02ea6d10836f0a3a4f6dd4af90ff23` (`Initial commit`). Initial
`git status --short` was empty. The only tracked file was the 14-byte
`README.md`, containing `# 3DPS-MiniApp` without a trailing newline.

Read-only remote discovery found:

| Origin branch | Observed commit | Tree |
|---|---|---|
| `main` | `3a6da2d6df02ea6d10836f0a3a4f6dd4af90ff23` | `README.md` only |
| `DaemionBladee-dev` | `d758653d940124760e5cd7e9b02071a9ba3ce805` | `README.md` and `3DPS-MiniApp_Codex_Instructions_LOGIC_VERIFIED_v1.4.zip` |

The requested root contracts were absent from the checkout. The development
branch was fetched without switching/resetting the work branch. Its archive
contains 34 Markdown entries (root instructions/README, 14 docs, 18 prompts),
not an application bootstrap. Archive SHA-256:
`f5ff785ff63e934077a6d843a7d32ab8ce72ccef7c9295ddb78a7f0b2739c1f9`.

To make the requested contracts available at their documented paths, this M00
change materializes the archive's `AGENTS.md`, `docs/` and `prompts/` (33 files).
It preserves the existing root README and does not add the binary archive.
All imported files remain byte-identical to the archive except the explicitly
updated `docs/OPEN_DECISIONS.md`. This import is documentation, not evidence
that any described feature exists. No earlier prototype was found in either
observed branch tree. Other repositories, private deployments and databases
were not inspected; none were supplied as audit targets.

Required contracts read: root `AGENTS.md`, `MASTER_ROADMAP`, `STATE_MACHINES`,
`INTEGRITY_RULES`, `DEPENDENCY_MATRIX`, and `prompts/M00_REPOSITORY_AUDIT.md`.
Supporting architecture, product, business, data, API, frontend, security,
payment, DevOps and open-decision documents informed this baseline.

## 2. Actual file inventory and classification

Before M00:

```text
3DPS-MiniApp/
└── README.md
```

Review tree after M00 (Git metadata excluded):

```text
3DPS-MiniApp/
├── .env.example                         # new, inert safe configuration template
├── .gitignore                           # new, excludes local environment files
├── AGENTS.md                            # imported v1.4 contract
├── README.md                            # existing, unchanged
├── docs/
│   ├── API_CONTRACTS.md
│   ├── ARCHITECTURE.md
│   ├── BUSINESS_RULES.md
│   ├── DATA_MODEL.md
│   ├── DEPENDENCY_MATRIX.md
│   ├── DEVOPS.md
│   ├── FRONTEND_SPEC.md
│   ├── IMPLEMENTATION_BASELINE.md        # M00 output
│   ├── INTEGRITY_RULES.md
│   ├── MASTER_ROADMAP.md
│   ├── OPEN_DECISIONS.md                 # imported + M00 review register
│   ├── PAYMENTS_COMPLIANCE.md
│   ├── PRODUCT_SPEC.md
│   ├── SECURITY.md
│   ├── STATE_MACHINES.md
│   └── adr/0001-project-baseline.md       # M00 output
└── prompts/
    ├── M00_REPOSITORY_AUDIT.md
    ├── M01_MINIAPP_FOUNDATION.md
    ├── M02_TELEGRAM_AUTH.md
    ├── M03_CORE_DATABASE_API_AND_TRANSACTION_FOUNDATION.md
    ├── M04_SECURE_CUSTOMER_PRINTING_INTAKE.md
    ├── M05_DESIGN_INTAKE_AND_COMBINED_STAGE_LINEAGE.md
    ├── M06_ISOLATED_SLICING_AND_MODEL_ANALYSIS.md
    ├── M07_DESIGN_AND_PRINT_PRICING_PLUS_LEVEL_2_ELIGIBILITY.md
    ├── M08_OWNER_REVIEW_VERSIONED_OFFER_ACCEPTANCE_AND_NOTIFICATIONS.md
    ├── M09_SIMULATION_STAGE_ORDERS_AND_PAYMENT_INTEGRITY.md
    ├── M10_REAL_INVENTORY_AND_SAFE_SPOOL_RESERVATIONS.md
    ├── M11_PRINTER_CLASS_CAPACITY_HOLDS_AND_OWNER_ASSIGNMENT.md
    ├── M12_PRODUCTION_ATTEMPTS_QC_PHYSICAL_AND_DIGITAL_FULFILLMENT.md
    ├── M13_NOTIFICATION_RETRY_SUPPORT_AND_FINANCIAL_REPORTS.md
    ├── M14_SECURITY_CONCURRENCY_RECOVERY_AND_COMPLETE_E2E_AUDIT.md
    ├── M15_CONTROLLED_HTTPS_STAGING_PRODUCTION_INFRASTRUCTURE.md
    ├── M16_HARDWARE_CALIBRATION_AND_SAFE_MANUAL_LIVE_LAUNCH.md
    └── TASK_TEMPLATE.md
```

| Component | Classification | Actual evidence / recommendation |
|---|---|---|
| Root README | existing | Title only; preserve. Add tested run instructions in M01, not fictional commands now. |
| v1.4 specifications/prompts | existing requirements after import | Proposed architecture, not executable behavior. Review with this baseline. |
| Python API, bot, shared services, worker | missing | No Python source, manifest, lockfile or executable entry point. |
| Mini App/bootstrap | missing | No JS/TS/HTML/CSS, package manifest, lockfile, router or components. |
| PostgreSQL schema / Alembic | missing | No models, migrations, migration metadata, DB fixtures or connection configuration. No DB introspection performed. |
| Authentication / roles / ownership | missing | No initData verifier, sessions, CSRF, provisioned owner or backend access checks. |
| Docker / Caddy / CI / deployment | missing | No Compose/Dockerfile, service definitions or CI workflows. |
| Unit / integration / E2E tests | missing | No runners, test files or configured check scripts. |
| Quotes / payments / inventory / jobs | missing | Docs only; no handlers, records, ledgers or adapters. |
| Old demo/starter logic | prototype: none found | Nothing to reuse, delete, rewrite or migrate. Do not describe hypothetical demo bugs as findings. |
| Unsafe implementation | unsafe: none demonstrated | No running application was supplied. Exposing future placeholders as real services would be unsafe. |
| Existing-data conversion | needs migration: none identified | Later schema additions require Alembic; absence of a supplied DB is not proof no external DB exists. |

## 3. Workflow and integrity gaps

Every capability below is **missing in code**. These are acceptance obligations
for future milestones, not failed runtime tests or implemented safeguards.

| Agreed contract | Required implementation / validation | Milestone owner |
|---|---|---|
| Only `customer` and `owner`; owner is production operator | Explicit server-provisioned owner; no first-user grant; authorize each resource/action. UI shell is not authorization. | M01 shell; M02 identity; resource tests as domains arrive |
| `printing`, `custom_design`, `design_and_print` | Parent project and independent design/printing requests, never one universal paid/status field. | M03–M05 |
| Full stage payment before work | Design needs its own scope approval and payment, no printer/filament. Print needs its own verified payment and later approved assignment. | M05 simulation fixture; M09; M11/M12 |
| Exact immutable versions | Request revision/spec hash, file hashes, design approval, pricing/profile/calibration versions checked at issuance, acceptance and checkout; edits invalidate stale approvals/offers. | M04–M09 |
| Level 2 only for calibrated standard printing | Unknown/failure/special requirements -> review. Manual binding quotes require the binding gate too. No calibration, pricing or thresholds assumed from examples. | M06–M08; M16 activation |
| Informational vs simulation vs live | `test_estimate` has no accept/pay action. Simulation offers yield simulation orders only. Changing flags never upgrades records. | M07–M09 |
| One stage lineage | Project -> stage request -> quotation -> order -> one obligation -> attempts/credits; matching customer/project/stage/category/currency and semantic mode. | M03 primitives; later domain milestones |
| Design without STL | Zero print request items allowed; genuine `design_service` quote/order lines with nullable print-item FK and scope snapshot. | M05, M07–M09 |
| Combined service derivation | One idempotently derived print request from exact approved design version; design payment does not pay/release printing. | M05 then M09 |
| Financial credit truth | Immutable uniquely scoped external credit, usable by one obligation only; net verified funds and separate owner release. Receipt/invoice/client callback is insufficient. Decimal/NUMERIC; integral XTR; no mixed-currency totals. | M07, M09 |
| Digital vs physical commerce | Standalone in-Telegram digital design uses Stars; no manual-MMK workaround. Combined classification and physical methods remain undecided. All real collection remains off. | M09 simulation/sandbox; policy + live release gates |
| Checkout readiness vs physical assignment | Real printing checkout requires real spool and class-capacity holds; owner later approves compatible specific-printer window. Post-settlement resource loss -> audited hold/resolution/refund. | M09 mock; M10 stock; M11 capacity/assignment |
| Inventory/attempt/QC accounting | Item-scoped reservations, signed stock ledger, one consumption posting, new linked owner-approved reprint attempts, quantity-level QC before fulfillment. | M10–M12 |
| Scope-dependent design completion | Standalone digital delivery needs paid approved version and authorized private release; combined manufacturing-only scope need not transfer files. No fake shipment. | M05 scope; M12 delivery |
| Durable private processing and notifications | M04 pending task is not M06 analysis. Isolated parsers have no DB/bot credentials or printer network. DB state + audit + outbox commit together; notifications do not constitute truth. | M03/M04/M06/M08/M13 |

State machines must remain separate: request, special review, quotation, stage
order, payment obligation, payment attempt/credit, design project, stock hold,
capacity hold, physical assignment, production attempt, QC and fulfillment.
Implement actor/guard/version checks, audited exceptional transitions and
negative tests as each domain arrives. No transition service exists today.

### Contract discrepancies requiring review

These are documentation inconsistencies/underspecified cases, not code defects.
Details, proposed handling and decision deadlines are tracked as `M00-D01`–`D08`
in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

1. Integrity text says active **paid** order; AGENTS/API/data and concurrency tests require active **payable** order. Proposed baseline protects payable orders, with exact predicate/replacement flow still to approve.
2. `quotation_items.item_kind` is required by integrity rules but absent from the logical field list. Preserve real design lines, reconcile before schema generation.
3. Quote `mode=simulation_offer|binding_offer` differs from order/obligation `simulation|live`; define a typed mapping, never literal cross-table equality or record promotion.
4. Quotation API example uses `currency`; conventions use `currency_code`. Proposed wire name is `currency_code`, to freeze before generated clients.
5. Assignment transition table is incomplete; physical delivery status lists differ on `completed`/`cancelled`.
6. Refund entry/resume/partial-refund/dispute paths, especially after QC/fulfillment, need explicit guards. Never infer a path that continues work after a reversal.
7. Manufacturing-only combined design can complete without digital transfer, but design-project chain ends `approved -> delivered`; define its terminal semantics without inventing file rights.
8. M01 health-check wording is conditional on a backend that does not exist until M02/M03. Test frontend unavailable-state handling; do not add an out-of-scope toy backend or claim a health endpoint works.

## 4. Risk register

Priority expresses what must be prevented when implementation starts; no entry
claims a currently exploitable deployed service.

| ID / priority | Risk and evidence | Control / stop point |
|---|---|---|
| R01 / P0 | Specifications mistaken for implementation; initial main has only README. | This evidence baseline; require executable acceptance evidence per milestone. |
| R02 / P0 | Later code could enable binding quotes, funds or real printers without readiness. | Safe example flags; future fail-closed backend/schema gates; owner live signoff at M16. Template is not enforcement. |
| R03 / P0 | Mock role/navigation could become owner authorization. No auth exists. | M01 compile-time dev-only UI mock; M02 raw initData, provisioned owner, revocable hashed sessions, CSRF/Origin checks. |
| R04 / P0 | Multiple quote versions/orders, reused credit or cross-stage payment could duplicate liabilities. | M00-D01/D03; M09 stage lock/index and immutable credit uniqueness; PostgreSQL race tests. |
| R05 / P0 | Malicious files or unauthorized downloads could leak data/execute code. No storage/worker exists. | M04 private quarantine, ownership/format/archive quotas; M06 bounded isolation without credentials/network. |
| R06 / P0 | Mock holds might authorize live checkout, or paid orders proceed without resources. | M09 simulation-only adapter, M10/M11 real holds; audited hold/refund on resource loss. |
| R07 / P1 | Broad M03 migration could reference absent future tables or destroy external legacy data. | One incremental M02 Alembic chain; discover any external DB before migration; no speculative tables/FKs. |
| R08 / P1 | State/schema ambiguities could create invalid delivery/reversal paths. | Resolve D01–D07 before the affected migration/command; negative transition tests. |
| R09 / P1 | Digital pricing/payment/legal assumptions could produce noncompliant checkout. | Existing policy decisions remain pending; Stars-only rule for standalone digital; no provider or rate invented. |
| R10 / P1 | Cloud task mistaken for permanent hosting, real phone or hardware evidence. | Cloud static/tests only as supported; explicit device evidence and separate M15/M16 operations. |
| R11 / P1 | Credentials/data could be committed during later setup. | Local env ignore rules; no values in example; scoped test credentials out of band; future CI scans. |

## 5. Proposed architecture and migration baseline

See [ADR 0001](adr/0001-project-baseline.md), accepted as the architecture baseline
in the owner's M01 start instruction; individual unresolved items stay open.

Minimal future paths (not created as empty services in M00):

| Path / first milestone | Responsibility |
|---|---|
| `miniapp/` / M01 | Strict React/TypeScript/Vite; router/providers, components, Telegram adapter and API client foundation. |
| `backend/app/` / M02 | FastAPI adapters/config/auth, shared services/domain/data access; M03 adds business primitives. |
| `backend/alembic/` / M02 | Sole migration chain; M03 extends it. No second root migrations framework. |
| `backend/tests/` / M02 | Auth/domain tests, disposable actual-PostgreSQL migration and concurrency fixtures. |
| `telegram_bot/` / M02 | Python-importable Aiogram 3 adapter, long polling; shared services, no duplicate rules. |
| `backend/app/workers/` / M06 | Trusted dispatch/result handling and separately isolated parser/slicer execution. |
| `tests/e2e/` / M01 baseline | Browser checks; later full simulator E2E. |
| `deploy/`, `compose.yaml` / when runtime is introduced | Optional local Compose; later Caddy/Linux VPS hosting. Not implemented by M00. |

API direction: same-origin `/api/v1`, Pydantic/OpenAPI as canonical schema,
generated TypeScript types once schemas exist, opaque UUID identifiers,
UTC offset-bearing timestamps, decimal strings for money, bounded pagination.
Propose consistent `{code, message, details, correlation_id}` errors and typed
401/403/404/409/422/413 responses. Mutations use session/CSRF checks;
side-effect commands use scoped idempotency keys and expected versions.
M01 must not fabricate an OpenAPI backend or handwritten domain DTOs and call
them generated. Resolve D03/D04 before the affected contracts are generated.

There is no legacy schema to convert in this checkout. M02 should introduce
only auth users/sessions plus the single Alembic environment. M03 adds minimal
projects/requests and transition, transaction, audit, idempotency and outbox
primitives. Later migrations add domain tables incrementally; the M05
`source_design_version_id` FK follows creation of `design_versions`.
Review upgrade SQL, test empty and prior-revision seeded PostgreSQL upgrades,
rollback/recovery and preservation of historical records. Never use production
`create_all()`, reset data, or discover/migrate a remote DB implicitly.

Deployment target remains one modular monolith with thin API/bot adapters,
PostgreSQL as truth, private files and isolated processing. Only the HTTPS
gateway is public; DB, queue, worker and printers remain private. No Kubernetes
or microservices are justified. Cloud workspaces are isolated development tasks,
not always-on hosting. CachyOS is optional; VPS/HTTPS/restore/device/hardware
validation belong to later gates. No Docker/DB/service connectivity was needed
or validated during M00.

## 6. Dependencies that must not be skipped

- **M02 -> M03:** M02 owns auth persistence and PostgreSQL fixtures; M03 reuses
  the same users/session/Alembic chain, never a second schema bootstrap.
- **M03 outbox -> M08 first notifications -> M13 retries/reporting:** domain
  change, audit and event write share a transaction; delivery is at-least-once
  with idempotent consumers. No bot message is the financial source of truth.
- **M04 pending tasks -> M06 execution:** queued/pending is not analyzing.
- **M05 design scope -> M07 independent design-pricing basis -> M08 issued
  quote/acceptance -> M09 atomic stage order + obligation -> M12 secure release.**
  M05 may use explicit paid simulation fixtures only; M08 does not claim order
  or payment creation. Acceptance retries must not duplicate records; different
  accepted versions of one stage cannot create competing payable orders.
- **M09 simulated stock/capacity -> M10 real item/spool holds -> M11 real class
  capacity holds and owner-approved non-overlapping physical assignment.**
  Both real availability adapters must be integrated/tested before any live
  physical checkout, with policy/launch gates also satisfied. Capability work
  is not permission to collect funds. Design-only work has no stock adapter gate.
- **M10/M11 -> M12:** attempts/reprints, partial QC, stock usage and distinct
  physical/digital completion must reconcile before fulfillment.
- M14/M15 security, restore and actual Telegram tests precede M16 owner-approved
  manual live launch; Level 2 auto-issuance is a separate subsequent switch.

## 7. Checks performed and limitations

Actual commands/checks in this audit:

| Check | Observed result |
|---|---|
| `git status --short` before changes | Exit 0, empty output: initially clean. |
| `git log -3 --oneline`, `git branch -avv`, `git ls-files` | Initial commit `3a6da2d`; `work` checked out; only `README.md` tracked. |
| `git ls-remote --heads origin` | Exit 0; exactly the main/development refs and SHAs recorded above. Git read access works. |
| `git fetch origin DaemionBladee-dev`; `git ls-tree -r --name-only FETCH_HEAD` | Exit 0; development tree contains only README and instruction ZIP. No branch switch/reset. |
| `rg --files` / hidden-file and Git-tree inventory | No source/manifests/migrations/tests/CI/deployment/auth implementations. Initial requested-file search exited 1 because contracts were absent, not because an application test failed. |
| Python ZIP entry/path/type/content inspection and SHA-256 | 34 Markdown files, safe relative paths; imported 33 excluding README; hash above. |
| Tool versions | Git 2.52.0; Node v24.22.1; npm 11.9.0; Python 3.12.14. These are observed host tools, not project pins. |
| Final documentation/configuration checks | Python assertion-based audit checks exited 0 with the output below. `git diff --check` and `git diff --exit-code` exited 0 (tracked files only); untracked additions were inspected separately. |

Actual final static-check output (the Python audit inspected all 38 non-Git
files, including untracked additions):

```text
AUDIT_FILES 38
SOURCE_FILES 0
ARCHIVE_CONTRACTS_PASS 32 unchanged imports
README_PRESERVATION_PASS 14 bytes
NEW_FILE_WHITESPACE_PASS 4 files
LOCAL_MARKDOWN_LINKS_PASS 6
SAFE_ENV_TEMPLATE_PASS 14 names; all live gates false; credentials/quotas unset
ENV_IGNORE_RULES_PASS 4 local variants ignored; example reviewable
BASIC_SECRET_PATTERN_CANDIDATE_FILES 0
AUDIT_STATIC_CHECKS_PASS (not application tests)
```

The checks compared imported file bytes with the archive (excluding README and
the deliberately updated decision register), resolved relative Markdown links,
checked new-output whitespace, parsed environment names/defaults without
printing credentials, and used `git check-ignore` to verify local env exclusion
and the example exception. The limited credential-pattern scan covered current
files for common Telegram/GitHub/AWS tokens and private-key headers; zero
candidates does not establish comprehensive secret/history scanning. Final
`git status --short --untracked-files=all` shows 37 new files and no tracked
modifications, staged changes or deletions. Existing README bytes are preserved.

Python/frontend lint, typecheck, unit tests, build, Alembic, PostgreSQL race tests,
browser tests, Telegram initData/session/device tests, payment sandbox, slicer
and restore tests: **NOT RUN**. There is no application, manifest, schema,
fixture or configured suite to execute. M00 does not install arbitrary
dependencies, invent passing tests or start services to fill that gap. No
production database, wallet, bot, payment or printer operation was attempted.
No external credential values were read or logged.

## 8. Proposed M01 scope and following preconditions

**Stop here for owner review.** M01 starts only after this baseline, ADR and
decision register are reviewed/accepted. Live policy decisions can remain open
for unrelated frontend scaffolding; their named gates stay closed.

Prioritized M01 task:

1. Add `miniapp/` strict React/TypeScript/Vite with a pinned supported Node/package
   manager choice, committed lockfile and reproducible install scripts. Reuse
   nothing fictional; the audit found no bootstrap.
2. Add Tailwind and accessible reusable/shadcn UI foundation, React Router and
   TanStack Query; mobile/desktop customer `/app` and owner `/owner` shells only.
   Owner reviews/payments/production/inventory remain clearly inert placeholders.
3. Add Telegram adapter for theme light/dark, viewport/safe areas and back
   navigation; loading/error/empty/offline and normal-browser Telegram guidance.
   A deliberately enabled development-only **UI** mock must be absent/inactive
   in production builds and grant no backend identity or permissions.
4. Centralize relative `/api/v1` requests and configurable Vite `/api` proxy.
   Handle unavailable backend honestly. Defer real auth and generated domain
   types to M02/M03; never implement a fake health endpoint for M01 acceptance.
5. Add Vitest/RTL and Playwright baseline per roadmap, accessible responsive
   navigation/theme/back-button checks and production mock-exclusion evidence;
   typecheck/lint/unit/build commands and tested README run instructions.

Expected M01 changes: `miniapp/`, frontend-relevant `tests/e2e/`, lockfile,
tested root README instructions and justified ignore/config/CI files. No
business schema, bot payment handlers, upload processing or pricing engine.
Report exact runner counts/results and unsupported checks. Real Telegram
phone/cookie evidence remains pending for M02/G1.

Before M02: M01 acceptance/review; choose pinned Python/PostgreSQL tooling and
disposable DB fixture; approve UUID/session persistence and auth security
parameters (freshness/expiry/CSRF/Origin/rate limits); securely provision only
test bot/owner identity when actual Telegram tests require them. Generated
synthetic auth vectors can be tested without asking for real credentials.
Device HTTPS/BotFather setup needs external evidence; no G1 pass without it.

Before M03: M02 auth/session/CSRF/owner checks and initial Alembic chain actually
pass against PostgreSQL; M00 migration direction accepted; approve minimal
project/request transition and API/error/idempotency contracts; reuse auth
fixtures, add transactional audit/outbox rollback tests and generated TS
contracts. Unresolved business predicates must be closed before their own
tables arrive, not guessed in a speculative all-domain migration.

## 9. Review and rollback

Review targets: requirements import provenance; proposed ADR/path/UUID/API and
incremental migration direction; D01–D10 decision deadlines; scoped M01 plan.
No pricing, hardware, legal classification, provider availability or release
approval is inferred. Root README and tracked application history are unchanged.
This change adds documentation and inert configuration only; there are no DB
migrations or runtime effects to roll back. No commit/push/deployment performed.
