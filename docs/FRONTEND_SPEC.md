# React + TypeScript Telegram Mini App — frontend specification

## Implemented M05 design workflow

Customer `/app/requests/design` creates a design-only or combined draft;
`/app/design-projects/:id` autosaves briefs, uploads private references and submits
without print items. Scope agreement and proof reviews name exact versions.
Owner `/owner/designs/:id` proposes scope, explicitly activates simulation work,
publishes immutable previews and converts an approved manufacturing version once.
The derived draft reuses M04 specs/submission, with source downloads denied and
independent progress. Proof viewer renders only authenticated images or escaped
plain text. No localStorage data, digital release or live action is introduced.
See [DESIGN_INTAKE.md](DESIGN_INTAKE.md).


## Implemented M04 printing workflow

`/app/requests/new` creates a private printing draft; `/app/requests/:requestId`
resumes its Models, Specifications, Fulfillment and Review steps. Per-item settings
and preferences autosave through versioned backend APIs. Uploads report actual
transfer progress, structural-validation errors and retry/cancel controls. A
reload retrieves committed drafts from PostgreSQL; file bytes and draft data are
never written to localStorage. Interrupted in-memory transfers require reselection.
`/owner/requests/:requestId` is read-only inspection with private downloads and
pending-analysis status. Owner authorization is enforced by FastAPI. Development
catalog choices are visibly labeled; no pricing/checkout actions exist. See
[PRINTING_INTAKE.md](PRINTING_INTAKE.md) for test/run instructions.

## Structure
One React SPA, two workspaces (`customer`, `owner`). Do not implement an operator role or separate operator dashboard for MVP. Owner handles production and admin functions. Use route guards for navigation, but authorize every API call on FastAPI.

Tech: React, TypeScript strict, Vite, Tailwind CSS, accessible components (shadcn/ui optional), React Router, TanStack Query, React Hook Form + Zod for complex forms, OpenAPI-generated TypeScript types, Telegram Mini Apps SDK. Optional Three.js viewer after core order processing works; never block ordering because browser cannot display a model.

## Routes
### Customer
| Path | Screen |
|---|---|
| `/app` | Home and current order summary |
| `/app/requests/new` | Service selection |
| `/app/requests/print` | Print wizard: upload -> item configuration -> review |
| `/app/requests/design` | Design brief wizard |
| `/app/requests/:id` | Draft/resume, request status and analysis |
| `/app/quotations` | My quotations |
| `/app/quotations/:id` | Quote details, expiry, accept/change/decline |
| `/app/orders` | My orders |
| `/app/orders/:id` | Stage-specific status and timeline; never show print queue for design-stage order |
| `/app/design-projects/:id` | Design proof approval, scope, revisions and authorized digital deliverables |
| `/app/orders/:id/payment` | Stage-specific permitted checkout or simulated payment; never MMK bank-transfer checkout for digital-only in-Telegram services |
| `/app/profile` | Profile / contact / address |
| `/app/support` | Support thread |

### Owner
| Path | Screen |
|---|---|
| `/owner` | Queue summary: reviews, payments, assignments, failures, low stock |
| `/owner/reviews` and `/:id` | Special order review, clarification, revise, reject |
| `/owner/quotations` | Auto/manual quotation history and pricing details |
| `/owner/orders` and `/:id` | Orders and snapshots |
| `/owner/payments` and `/:id` | Verify payment evidence against actual funds |
| `/owner/designs` and `/:id` | Design briefs/versions/customer approvals/digital delivery |
| `/owner/production` | Work queue and owner-as-operator controls |
| `/owner/jobs/:id` | Job details, start/pause/complete, failures, QC |
| `/owner/printers` | Virtual profiles / future physical assets |
| `/owner/inventory` | Materials, spools, reservations and movements |
| `/owner/reports` | Summary and material-cost metrics |
| `/owner/settings` | Pricing policy and owner-only feature gate state |

## UX
- Use Telegram theme variables, light/dark modes, safe-area insets, resize handling and native back navigation where available.
- Mobile-first cards and sticky primary actions; tablet/desktop responsive tables and sidebars.
- State-specific handling: loading, empty, permission denied, offline/retry, expired session, invalid/stale quote, failed upload and manual-review messages.
- Use inline validation and concise labels; customers can choose `Not sure` for technical settings, triggering owner review.
- Multi-file upload progress, cancel/retry, private thumbnail/preview if safe. Confirm inferred model units/dimensions before quoting.
- Persist order drafts in PostgreSQL using debounced API saves; do not persist customer models or auth data in localStorage.
- Do not present fabricated progress %. Real status milestones can be shown even when printer has no telemetry.
- Explicitly label `test_estimate`, `simulation_offer`, and `binding_offer` differently. Simulated offers can be accepted only into mock orders for testing; never show a real pay button for them. Owner manual quote screens must also respect backend `BINDING_QUOTES_ENABLED` (not just `AUTO_QUOTE_ENABLED`). Separate payment instructions for physical vs digital categories and currency; owner-approved payment policy controls available options. For **printing-stage checkout**, display the server-returned hold/availability state, block payment if reservation is missing/expired, and explain any post-payment owner hold/refund. **Do not show printer/inventory prerequisites for design-only payment.** Backend enforces all gates. Show explicit `on_hold`/refund states and the real capacity-hold expiry separately from owner-approved printer assignment. Design quote and delivery screens must work with **zero print items**.

## Shared components
- Layout: `AppShell`, `MobileBottomNav`, `DesktopSidebar`, `PageHeader`, `TelegramBackButton`, `TelegramThemeProvider`, `SafeAreaContainer`.
- Auth/status: `AuthGate`, `RoleGuard`, `PermissionGate`, `LoadingState`, `EmptyState`, `ErrorState`, `StatusBadge`, `ConfirmDialog`.
- Request: `ServiceTypeCard`, `PrintRequestWizard`, `FileUploadDropzone`, `ModelFileCard`, `ModelDimensionsForm`, `MaterialSelector`, `ColorSelector`, `QualityPresetSelector`, `QuantityInput`, `SpecialRequirementsForm`, `RequestSummary`.
- Commerce: `QuotationCard`, `QuoteExpiryTimer`, `OrderTimeline`, `ReceiptUpload`, `PaymentStatusPanel`.
- Owner: `ApprovalPanel`, `FlagReasons`, `CostBreakdown`, `PrinterRecommendationCard`, `ProductionJobCard`, `FailureReportForm`, `SpoolStockCard`, `StockMovementTable`.

## Feature directory plan
```
miniapp/src/
  app/ {router,providers,shell}
  pages/ {customer,owner}
  features/
    auth/ requests/ design/ files/ models/ quotations/
    payments/ orders/ reviews/ printers/ inventory/ production/
  components/ {ui,shared,layout}
  integrations/telegram/
  lib/ {api,auth,errors,format,validation}
  hooks/ stores/ styles/ tests/
```
- Each feature owns `api.ts`, `hooks.ts`, `schemas.ts`, components and tests where useful.
- Server cache via TanStack Query; local UI state via React state. Add Zustand only if cross-page state becomes complex.
- Generate TS types from FastAPI OpenAPI, not mirrored manual interfaces. All API calls through one client with credentials and error normalization.

## Telegram-specific integration
- Bot menu button and Main Mini App open the same HTTPS app. Owner notifications link to review/payment/job paths through appropriate Telegram launch URL. Treat route IDs as untrusted navigation hints.
- Obtain raw `initData` from SDK and send to backend auth endpoint; never use `initDataUnsafe` for authorization.
- Production should not ship browser mock auth. Local component/E2E testing can use an explicit dev-only mock adapter on a local-only backend. Codex Cloud may run mock browser tests, but real Telegram phone integration must be recorded as pending unless actually demonstrated.
- Normal browser must show helpful "Open in Telegram" guidance unless development mock mode is deliberately enabled.
- Test with actual Telegram Android, iOS and Desktop, especially cookie persistence, keyboard behavior, safe areas and file uploads.

## F01 acceptance
- Build renders two responsive workspaces, selected by mock test context only.
- CI: TypeScript, ESLint, Vitest/RTL, Vite build pass.
- No real business actions, no production auth bypass, no physical printer remote controls.

## F02 acceptance
- Telegram signed raw initialization data verified in FastAPI; server session created and revoked; current user loaded; owner API rejects customer.
- Deep links resolve to authorized pages; no secrets in frontend bundles.

## Implemented M06 interfaces

Submitted printing details display waiting, processing, completed, clarification,
manual review or failure from real authenticated APIs. Current results show
calculated/customer-confirmed dimensions, volume/topology, virtual profile/version,
per-model grams/duration, quantity and warnings, always labeled
“Simulation estimate — not a final quotation.” Owner processing queue and bounded
retry review use the existing API client, sessions and generated TypeScript types.
No quote acceptance, checkout, payment, G-code or printer control is exposed.

## M07 implementation boundary

Implemented M07 detail panels show backend-calculated test estimates, independent MMK/XTR stages, review/missing-input states and Owner-only cost/provenance details. The Owner dashboard has explicit versioned simulation configuration. React does not compute authoritative prices or persist sensitive pricing data in localStorage.
