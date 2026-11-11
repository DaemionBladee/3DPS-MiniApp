# AGENTS.md — 3DPS-MiniApp (project-wide Codex instructions)

> Applies to all work in this repository. This file is the **short, always-on contract**.
> Consult the detailed files in `docs/` for requirements and design. Do not infer that a requirement is implemented merely because it is documented.

## Codex execution environment
The owner uses **Codex on the website (Codex Cloud)** with a private GitHub repository. `AGENTS.md` must be at the repository root. Cloud tasks are isolated; review and save/merge changes in GitHub before relying on them in a different task. Do not assume cloud tasks provide an always-on server, Docker daemon, a public HTTPS tunnel, or actual Telegram phone testing. CachyOS is an **optional** local development/test environment. Never require Codex CLI for task completion.

## Mission and current stage
Build 3DPS-MiniApp, a **Telegram-first 3D printing and custom 3D design order management system**, using one Telegram bot, one React/TypeScript Mini App, one Python/FastAPI business backend, and PostgreSQL. The business starts with **one person acting as owner and production operator**, and **no physical 3D printers yet**. Use virtual printer profiles and simulated production until real hardware is onboarded and calibrated.

## Authoritative project decisions — do not silently change
1. **Two MVP roles only:** `customer`, `owner`. The owner performs all operations. No separate operator UI; keep permission design extensible for future staff.
2. Services: `printing`, `custom_design`, `design_and_print`.
3. **Level 2 automated standard quotations:** only fully eligible, validated, configured standard printing requests may be auto-issued *after real printer/cost calibration and explicit live quotation + auto-quote feature gates*. All other requests require owner review. Before hardware calibration, show **NON-BINDING TEST ESTIMATES**, or strictly labeled **SIMULATION OFFERS** for end-to-end software tests only.
4. The owner must manually approve **special requirements**, manually **verify actual payment**, and manually **approve printer assignment**.
5. **Full payment in advance for each paid stage**. Combined design+print uses separately quoted and paid design/print stages, tied by a parent service project. Do not start actual design work or printing until **that stage’s** payment is verified; simulation may use only explicitly simulated payments. **Digital design sold inside Telegram must follow the Telegram Stars rules**, whereas physical prints follow physical-goods payment rules; see `docs/PAYMENTS_COMPLIANCE.md`.
6. Inventory by material variant and spool weight with ledger, reservations, consumption and waste. Failed jobs require owner review before reprints. QC precedes fulfillment.
7. Customer and owner work in the same Telegram Mini App; the Aiogram bot handles launch buttons, alerts and links to authorized pages. No everyday localhost admin dependency.
8. **Never automatically start a physical printer**. Until real machines are installed, all printer/job state is explicitly simulated.
9. Keep data and models private. Treat user-uploaded STL/3MF/OBJ and reference files as untrusted.
10. Source of truth is PostgreSQL and backend domain services, **not** client state or Telegram FSM.

## Technology decisions
- Frontend: React, TypeScript (strict), Vite, Tailwind, React Router, TanStack Query; use accessible reusable components. Add libraries when justified.
- Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2 async, asyncpg, Alembic, pytest.
- Telegram: Aiogram 3, long polling initially; Telegram Mini Apps signed `initData` verified on server.
- Persistence: PostgreSQL; private file storage (local volume in development; private durable storage in production).
- Worker: Python background worker / queue for file validation, model analysis and slicer invocation; isolate untrusted workloads.
- Slicing: adapter abstraction, PrusaSlicer first, OrcaSlicer optional; version and pin approved profiles.
- Runtime: Docker Compose locally on CachyOS; production Linux VPS with Caddy HTTPS, private services, encrypted off-server backups.
- Architecture: **modular monolith**. Don't introduce microservices/Kubernetes without a demonstrated need and owner approval.

## Repository navigation
Read only what is relevant to each task, but always consult this file and the milestone definition. `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md` are normative implementation contracts; reconcile conflicts before writing migrations:
- `docs/PRODUCT_SPEC.md` — product scope, roles, features and acceptance criteria.
- `docs/BUSINESS_RULES.md` — business workflows, approval gates and invariants.
- `docs/STATE_MACHINES.md` — exact stage-specific state transitions, guards and exceptional states.
- `docs/INTEGRITY_RULES.md` — transactional relationships, financial ledger and cross-entity integrity.
- `docs/DEPENDENCY_MATRIX.md` — upstream milestone boundaries, interface readiness and stop points.
- `docs/ARCHITECTURE.md` — components, directories, events, runtime boundaries.
- `docs/DATA_MODEL.md` — entity relationships, constraints and transaction strategy.
- `docs/API_CONTRACTS.md` — REST conventions, endpoint plan and response shapes.
- `docs/FRONTEND_SPEC.md` — routes, UI, Mini App interactions and component design.
- `docs/SECURITY.md` — Telegram auth, RBAC, uploads, workers, payment, deployment.
- `docs/DEVOPS.md` — Codex Cloud workflow, optional CachyOS, Docker, testing, staging and backups.
- `docs/PAYMENTS_COMPLIANCE.md` — payment policy for physical prints, digital design and combined services.
- `docs/OPEN_DECISIONS.md` — tracked unresolved decisions and precisely which live release gates they block.
- `docs/MASTER_ROADMAP.md` — milestones M00–M16 and release gates.
- `prompts/` — ready-to-run Codex task instructions and task template.

## Code organization and quality
- Inspect existing source and tests **before** editing. Reconcile old starter/demo files; do not overwrite working code or move whole directories without a migration plan.
- Business logic in domain/application services, not FastAPI route functions, React components, or Aiogram handlers. API and bot call the same services.
- Define typed Pydantic request/response schemas; use OpenAPI-generated frontend types. Version APIs under `/api/v1`.
- Use `Decimal` + PostgreSQL `NUMERIC` for money, UTC timezone-aware timestamps, explicit MMK rounding policy, DB-generated unique keys, and bounded pagination.
- Implement status transitions through validated services. Record immutable versions of issued quotes, approved model designs, pricing policies and key audit events. **Use schema-level `simulation` vs `live` separation for quotes/orders/payments**, not only UI labels or a global toggle.
- Use Alembic for schema changes. Do **not** use `create_all()` as a production migration strategy. Schema changes require upgrade and migration/recovery review. **M02 owns users/sessions, M03 creates only initial projects/requests plus shared transaction/audit/outbox primitives; M04–M12 add domain tables incrementally in the same Alembic chain.**
- Use explicit dependency injection for DB sessions, auth and configuration. Never trust client-supplied ownership, price, role or paid status.
- Prefer least privilege and small changes. Avoid circular imports, global mutable state, silent exception swallowing or needless dependencies.
- Security checks must be on **every** relevant backend API. Frontend route guards alone are not security.
- Defer features not in the current task. Do not convert planned endpoints/flows into claims that they work.

## Mandatory safety and financial gates
- No **binding quotations of any kind (manual or automated)**, live payment collection, real printer jobs, or public checkout before launch gates. `BINDING_QUOTES_ENABLED` controls all live binding quotations; `AUTO_QUOTE_ENABLED` additionally controls automated issuance. Both default false. Simulation may create labeled **test offers, test orders and test payments** for end-to-end testing only; the backend must make conversion into live obligations impossible.
- Receipt upload is **not** proof of paid status. Owner must verify real funds before stage activation. Provider events (including Stars) require verified, idempotent event handling; any future automated confirmation needs explicit product-policy approval. **Do not present MMK/manual-bank checkout for standalone digital design inside Telegram as a Stars workaround**.
- **Stage-specific release conditions:** a paid **design** stage may begin only after its own verified payment and cleared scope/review; it does **not** need filament stock or a printer assignment. Digital design delivery must reference the exact customer-approved version and authorized release. A paid **printing** stage additionally requires feasible material/capacity checks, transactional spool + capacity holds, and owner-approved physical printer assignment before production. Before offering real checkout, revalidate both real stock and capacity; **M09 mocks cannot authorize live checkout before M10/M11**. If settlement succeeds but inventory/assignment later fails, put the order on explicit `on_hold` and resolve/refund through an audited owner process, never silently begin production.
- Fail closed: missing/malformed model data, missing compatible profile, timeout, uncertain pricing, failed inventory reservation, stale quote or ambiguous requirements -> manual review/hold.
- Approval must bind to exact request/model/specification and quotation versions; material edits invalidate stale approvals.
- Owner overrides, payment actions, refunds, inventory adjustments and reprint decisions require reasoned audit entries and idempotency/concurrency protection. A **confirmed bank/provider credit may satisfy only one payment obligation**, enforced with an immutable credit ledger and unique transaction keys. One stage may have only one active payable order absent an approved replacement/refund flow.
- **Milestone dependencies must be real:** M04 persists pending analysis without claiming M06 worker exists; M05 models/scopes design, M07 provides manual design-pricing basis, M08 quote issuance, M09 payment, M12 secure digital delivery; M03 establishes minimal transactional outbox for M08 notifications, with M13 retry/reporting. M09 uses a **simulation-only** stock/capacity adapter; M10 and M11 implement real holds. Do not assume a later milestone already exists.

## Security baseline
- Verify Telegram's **raw** `initData` server-side using the official protocol, a fresh `auth_date`, and the server-only bot token. Never trust `initDataUnsafe` or a role sent from React.
- Provision the owner identity on the server; never assign owner to the first user or through a public form.
- Use secure, HttpOnly, SameSite cookies with CSRF defense and server-side session revocation. No long-lived secrets in frontend or localStorage.
- Resource ownership checks on every request, order, quote, file and payment retrieval/mutation; log sensitive admin actions.
- Authenticate all file download URLs; inspect formats, enforce size and 3MF decompression limits; store privately; parse/slice only in isolated bounded workers with **no printer network, bot token or DB credentials**.
- Keep DB/Redis/internal workers off public ports. HTTPS gateway is the public entry. Restrict CORS, CSP, rate limits, uploads and request sizes.
- Separate dev, staging and prod secrets/data. No mock Telegram identity in production builds.
- Never commit `.env`, secrets, customer model files, dumps or payment receipts. Don't print secrets in logs or test output.

## Workflow for each Codex task
1. Read `AGENTS.md`, milestone in `docs/MASTER_ROADMAP.md`, and task-relevant docs. Check Git status and existing implementation.
2. Produce a short plan: intended changes, affected files/contracts/migrations, security risks and tests. For a straightforward scoped task, proceed; ask for approval before destructive/irreversible work, production actions or policy changes.
3. Implement the **smallest end-to-end vertical slice** for the task, with tests and docs updated. No opportunistic unrelated rewrites.
4. Run the relevant available checks. If a command/tool is unavailable, state precisely what wasn't run and why; don't claim success.
5. Report: changes and files, migrations, tests with outcomes, known limitations, security implications, next recommended task. Do not mark unfinished features complete.
6. Commit only when the owner requests it or when the explicitly provided task directs a commit. Never force-push, reset the repository or drop production data without permission.

## Definition of done (for each milestone)
- Acceptance criteria in roadmap met; domain tests and negative/security tests added.
- Python lint/type/test and frontend TypeScript/lint/test/build pass where applicable.
- Alembic migrations reproducible and exercised in disposable PostgreSQL, including existing-data upgrades when applicable.
- Authorization and cross-customer isolation checked on all new endpoints.
- API contract and docs updated; evidence of testing reported.
- New feature is properly feature-gated where real payment/quote/production effects may occur.

## Start now
**First Codex task is M00** in `prompts/M00_REPOSITORY_AUDIT.md`. The user may have earlier prototype repositories or a Mini App bootstrap. Audit actual files before deciding what to reuse. Do not assume the current repository already implements anything described here.
