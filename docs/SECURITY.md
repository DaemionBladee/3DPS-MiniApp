# Security requirements and verification plan

Implemented security includes M02 verified Telegram sessions, M03 resource
permissions and M04 private uploads. See [AUTHENTICATION.md](AUTHENTICATION.md),
[PRINTING_INTAKE.md](PRINTING_INTAKE.md) and ADRs 0002–0004. Uploads are not
public/static assets. Structural validation runs with cleared environment,
closed inherited descriptors and resource limits; this is not a full OS sandbox.
Worker network/filesystem isolation and adversarial parser hardening remain
explicit prerequisites for M06 and public release. Later payment, production
and delivery controls below remain contracts, not implemented capabilities.

## Primary risks
- Forged Telegram identity; stolen Telegram session; owner impersonation.
- IDOR: customer reads/edits another customer's order/file/payment.
- Unsafe uploads (malformed STL/OBJ/3MF, compressed 3MF bombs, archive traversal) and crashes/RCE in parsers/slicers.
- Forged payment receipts, duplicate payment confirmations/refunds, **reused bank transaction credit across different orders**, unauthorized price changes.
- Inventory reservation race conditions and unauthorized printer control.
- Secret exposure, database/Redis exposure, inadequate backups and retention.

## Authentication
- Receive **raw** `Telegram.WebApp.initData` from React; verify on FastAPI using the **official Telegram HMAC flow** with the bot token held only on server. Reject duplicates, missing fields, invalid hash, future/expired `auth_date`, wrong bot context, malformed user ID.
- Check Telegram documentation for signed initData format (be careful: HMAC validation data-check-string differs from third-party Ed25519 mode). Prefer well-tested validation library with maintained upstream; pin and test known vectors.
- On success, provision normal customers by verified `telegram_id`; only operator-authorized configuration may grant `owner`. Owner ID must be explicitly configured/seeded via restricted out-of-band step. Never grant owner to "first user".
- Establish random opaque session ID; store only hash server-side, expire/revoke sessions, protect cookie with `Secure`, `HttpOnly`, `SameSite` and appropriate `__Host-` prefix on the HTTPS apex path.
- For cookie-authenticated mutations, implement CSRF protection (synchronizer token or a correctly bound double-submit pattern) **plus Origin/Referer validation as defense in depth**; also validate Origin for the login endpoint that creates the session. Disable cross-origin credential access by default; keep Mini App and API same-origin.
- Don't store bot token or session identifier in localStorage; avoid secret logs, query strings and analytics payloads.
- Owner account: protect Telegram login with 2-step verification and device lock; step-up confirmation on high-impact operations if feasible.

## Authorization
- Backend policy per action: customer can manage only owned drafts/quotes/orders/files; owner can manage all resources, with audit. Validate both role and relationship at DB query/service layer.
- Deny by default; tests must cover guessed entity IDs, user switching, expired sessions, owner-only mutations, and file download paths.
- Never rely on React route guards, button visibility, URL path, `role` JSON field or Telegram `start_param` as proof of authorization.
- All owner approvals and payment verifications record actor, reason, timestamp and relevant versions.

## File handling and slicers
- Allowlisted formats by actual content: STL, 3MF, OBJ, limited reference image types. Validate size, count, archive entries, decompressed size and ratios; reject nested/unsafe 3MF entries, symlinks/path traversal and suspicious resources. Establish upload quotas per user.
- Store raw files in private quarantine with generated storage keys; never serve user-uploaded names directly as paths. Clean and sanitize display names.
- Workers operate with non-root identity, read-only root filesystem where possible, dropped Linux capabilities, restrictive seccomp/AppArmor where available, resource limits, bounded timeout, bounded logs, no shell injection, and no network egress or secrets (especially bot token, DB credentials and printer API credentials).
- For increased risk and external uploads, isolate parsing/slicing in a separate VM or strong sandbox; Docker alone is not a complete isolation guarantee.
- Material geometry/scale warnings -> manual review. Do not allow customer-controlled G-code/config to be executed as trusted printer commands.
- Private downloads require current authenticated user and per-file owner/owner-role check. Any signed URL must be short-lived and scoped.

## Finance and business integrity
- A screenshot is evidence, **not payment confirmation**. Owner checks actual bank/payment record; backend records verification and transaction reference with audit.
- Full stage payment before work; payment status and order status independent. Separate `simulation` and `live` records; a test offer, receipt or payment cannot be promoted to live on feature-toggle changes. Duplicates blocked using idempotency keys, provider charge IDs and unique constraints.
- Pricing engine versioned, deterministic with Decimal/NUMERIC; all binding quotes (even manual) require `BINDING_QUOTES_ENABLED` and relevant category gate; automatic final quotes additionally require `AUTO_QUOTE_ENABLED`, model validation and calibration. Unknown -> owner review.
- Admin pricing changes, refunds and reservation adjustments audited. Use immutable `payment_credits` with unique normalized provider/account/transaction keys; check bank reference uniqueness against the actual payment method, and reject double credit across concurrent attempts. Prevent competing owner approval requests from both committing. For **printing-stage checkout**, verify valid **real spool and capacity** holds before charging; M09 simulated adapter can never authorize a live payment before M10/M11 and record safe, auditable hold/refund resolution if payment succeeds but stock/assignment fails. **Design-only stages do not depend on printing stock or printer assignment.** Digital-only design purchases inside Telegram require Telegram Stars (`XTR`); physical-print payment methods are separately reviewed. See `docs/PAYMENTS_COMPLIANCE.md`.
- Sensitive ownership changes/payment destination updates require explicit owner confirmation and audit.

## Runtime and deployment
- Public: Caddy HTTPS gateway only; allow SSH from restricted sources and only when necessary. No public Postgres 5432, Redis 6379, FastAPI 8000, slicer worker or printer control interfaces.
- TLS certificates automatically renewed, HTTPS redirect, HSTS after validation, relevant CSP/security headers, cookie defenses, upload size and API rate limiting.
- Run pinned supported images, non-root users, minimal packages, no exposed Docker socket to app containers; use CI vulnerability scanning and routine dependency updates.
- Separate dev, staging, production credentials, data and feature flags. Never connect staging to real printer or production payment provider.
- Backups: encrypted off-site DB + object/file storage; defined RPO/RTO; regular restore test in staging; rotate keys; documented incident playbook.
- Logs: correlation ID, event codes and sanitized metadata; do not log full models, passwords, signed Telegram initData, session cookies, payment receipts or secrets.
- Alerts: auth anomalies, repeated 403/401, worker crashes, low disk, failed backups, API unavailable, repeated payment verification failures.

## Minimum pre-release security test matrix
| Attack/failure | Expected behavior |
|---|---|
| Tampered Telegram initData | 401; no session |
| Expired/replayed initData outside allowed window | 401 |
| Customer GET `/owner/*` API | 403 |
| Customer changes `order_id` to another customer | 404/403; no data leak |
| Customer guesses private model file ID | 404/403 |
| Upload malformed STL / oversized 3MF archive | Reject or quarantine; no worker escape |
| User tries to submit role=owner | Ignored/forbidden |
| Payment receipt uploaded | Remains unverified |
| Customer tries `/payments/:id/verify` | 403 |
| Duplicate quote acceptance | One order only |
| Concurrent reservations for last filament | One succeeds; no negative balance |
| Concurrent capacity holds for last eligible printer window | One succeeds or owner hold; no time oversell |
| Two owner assignments target an overlapping physical printer time slot | Only one approved slot; second rejected or rescheduled |
| Same verified bank transfer referenced by two different orders | Second credit rejected; no double-paid obligations |
| Two accepted quote versions for one stage | Only one active payable order |
| Design service without any STL items | Valid design quote/order; secured digital delivery after paid/approved |
| Duplicate design-to-print conversion | Exactly one derived print request tied to approved design version |
| Mixed partial QC/reprints | Fulfillment requires ordered quantity QC-passed, no double-consumption |
| Printing checkout started with missing/expired stock hold | Reject before charging; require refreshed reservation |
| Payment settles but stock/capacity becomes unavailable | Owner hold, no production; audited reschedule/substitution/refund path |
| Design-only paid stage without a printer | Allowed after stage-specific verified payment and scope approval; no filament reservation |
| Stale approval after requirements edit | 409 / new review required |
| Slicer timeout/uncertainty | Manual review; no binding quote |
| Mock auth in production | Startup failure or explicit rejection |
| Simulation offer/payment after switching live flags | Still simulation-only; no real debit, real job or live order |
| Owner tries manual binding quote with `BINDING_QUOTES_ENABLED=false` | API refuses; only test estimate/simulation offer permitted |
| Owner tries live checkout before category-specific approval | API refuses; no payment obligation becomes payable |
| Digital design attempts MMK bank checkout in Telegram | API rejects by category; UI does not offer it |
| Telegram Stars callback is duplicated/tampered | Reject spoofed event; charge credited at most once |
| Production requests with no actual printer/calibration | Rejected; simulation-only |
| Database backup restored in staging | Complete and consistent restore |

## References
- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
