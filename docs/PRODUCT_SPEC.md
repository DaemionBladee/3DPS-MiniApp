# Product specification — 3DPS-MiniApp

## Vision
Build a Telegram-first small-business platform for quoting, ordering, design work, production and fulfillment of 3D-printed goods. The owner must be able to run daily operations from the Telegram Mini App on a phone, not depend on a local desktop dashboard.

## MVP actors
- **Customer:** Telegram user; submits private files/requests, updates drafts, sees their own quotations/orders, accepts quotes, submits payment evidence and tracks delivery.
- **Owner:** explicitly provisioned Telegram identity; manages everything: reviews, pricing policies, payment verification, printer allocation, inventory, production, failures, QC, support and reporting. The owner is also the operator.
- **Future staff:** not implemented in MVP. Permission vocabulary should allow later extension without redesigning business entities.

## Services
1. **Print existing 3D model:** customer supplies STL/3MF/OBJ, quantities, dimensions, material/color, quality preset, optional requirements and fulfillment choice.
2. **Custom 3D design:** customer supplies description, reference images, dimensions/intended use; owner scopes, quotes and produces versioned designs subject to customer approval.
3. **Design + printing:** design phase is approved and paid first; customer approves the model; a separate print quote and payment authorize manufacturing. Separate obligations and ledger entries.

## Customer experience
- Entry: bot profile/menu button or link opens Mini App inside Telegram.
- Home: New Request, Quotations, Orders, Profile/Support.
- New print: upload -> model details and scale confirmation -> quantity -> material/color -> quality -> special requirements -> fulfillment -> review -> submit.
- Drafts persist server-side and survive app closure; all items and file uploads are resumable with clear status.
- Validation/result: processing, failed input, clarification requested, standard eligible or owner review.
- Quote: itemized customer-visible specifications and total (not internal cost/profit); expiry; accept, decline, request changes.
- Payment: category-specific instructions only after approved valid binding offer acceptance and go-live approval. For digitally delivered design services sold inside Telegram use Telegram Stars; MMK bank/receipt entry must not be offered as an in-app workaround. Simulated orders show test-only mock payment; owner verifies actual settlement in live mode.
- Orders: printing-stage timeline (payment verified -> owner printer approval -> production -> QC -> physical delivery); **design-stage timeline** (payment verified -> scoped design -> customer approves exact version -> required contractual handoff, including authorized digital delivery **when promised**). Do not show printing states for design-only or fabricate print progress.

## Owner experience
- Unified owner home: Pending Reviews, Payments to Verify, Printer Assignments, Active Jobs, Low Stock, Orders, Design Projects, Reports, Settings.
- Owner receives private bot alert with a deep link to each action. Link is navigation only; API independently authenticates and authorizes.
- Review: see files, analysis, customer requirements, flags, cost basis, quote versions; approve, request clarification, revise or reject.
- Payment: compare transaction with actual bank/wallet records; verify/reject with audit note.
- Allocation: review compatible printer recommendations, assign/reassign; virtual profiles can simulate until hardware exists.
- Production: manually set start/stop/complete; record wastage/failure; authorize reprint; QC and fulfillment.

## Level 2 automatic quotation policy
- Automatic **final** quote only for standard printing, after go-live hardware calibration and explicit enablement.
- Suggested initial conservative rules (owner-configurable; not universally safe): one model/config, 1–10 copies; PLA/PETG approved stock; eligible color; validated STL or trusted 3MF import; standard-approved profile; adequate build volume and stock; bounded print duration (e.g. <=16 h); expected order total (e.g. <=100,000 MMK); normal deadline; no special needs; successful pinned slicer estimate.
- All rules must pass; unknown = review. Any owner flag, custom design, tight tolerance, nonstandard material, oversize, unsafe application, unstocked color, unusual deadline, geometry warning or unsupported finishing = owner review.
- Policy values are examples until owner calibrates and approves thresholds.
- No binding quote (manual or automatic) in simulation mode; show labeled **test estimates** or, for internal end-to-end testing only, an explicitly marked **simulation offer**. Neither can create real payment obligations.

## Critical workflow and financial rules
- 100% payment in advance for each stage. Owner verifies payments.
- Owner approves all physical printer assignments and all special-review exceptions.
- Owner reviews failed print before creating a reprint job.
- Stock managed by material variant + individual spool; reservation/actual consumption ledger.
- Production and customer orders remain distinct objects; one order item can produce many production jobs.
- Design and quotation versions remain immutable once issued/approved; edits create new versions. Combined design+print groups **two separately quoted, paid stage orders** under one service project. Design scope/service lines are valid without STL or filament; print request is created **once** from an approved design version. Simulation offers and test estimates never become payable records.
- Refunds and disputes require owner workflow and audit records.

## Non-goals until after MVP
- Third role/operator dashboard; online multi-shop marketplace; native Android/iOS app; unattended printer start; autonomous unsafe model repair; live camera streaming; sophisticated optimization; customer price calculators without validated slicer profiles.

## Quality attributes
- Private and secure by design; tolerates transient Telegram/web outages; can resume work; reproducible financial calculations and migrations; clear auditability; works on mobile Telegram clients; deployable without always-on personal laptop.
