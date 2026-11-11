# Payment classification and Telegram commerce compliance — release gate

**Status:** required pre-launch design decision. This is a technical product-policy checklist, **not legal advice**. Review current Telegram rules, provider terms and applicable local requirements before collecting money.

## Product classes
| Service | Expected deliverable | In-Telegram payment path | Launch decision |
|---|---|---|---|
| Physical 3D print | Printed/tangible item delivered or picked up | Physical goods/services rules; eligible supported provider/method as permitted | Validate supported provider/method and payment proof for actual location |
| Standalone custom 3D design | Digitally delivered STL/3MF/CAD files or digital design service | **Telegram Stars (`XTR`)** for digital goods/services sold within a Telegram bot or Mini App | Do **not** display MMK bank-transfer instructions or external payment workaround inside Telegram for this category |
| Design + physical print | Design work plus eventual tangible print, separately quoted and paid | **Ambiguous mixed/bundled classification requires a documented review.** Different stage obligations can use different currencies/methods. | Block live combined checkout until owner records approved classification and implementation |

**Default posture:** all real payment methods disabled before M16; show only simulated payment flows. Do not assume the physical-goods method applies to every custom-design service.

## Currency and stage model
- A parent `service_projects` record can group related design and printing stages.
- Each stage is represented by its own **order, quote and payment obligation**, linked to the parent. A stage has a single explicit `currency_code` and `payment_category` (e.g. `physical_goods` or `digital_goods`). No cross-currency arithmetic or assuming one MMK quote covers an XTR charge.
- Money for MMK-priced goods is stored as decimal minor/accounting units according to an explicit rounding policy; Stars must be represented as **integral XTR units**. Never infer conversions; if an exchange/conversion presentation is later needed, store rate source/time and show exact checkout currency.
- Payment attempts capture `method`, `provider`, `provider_charge_id` where applicable, owner action and verified provider evidence. A **separate immutable payment credit ledger** must make every bank transfer or provider charge usable for at most one obligation; duplicate references across different attempts are rejected or held for owner investigation. For Telegram Stars, create the invoice for the exact order/stage, handle `pre_checkout_query` (**validate buyer, payload, currency, amount, obligation, expiry and current status; answer within 10 seconds**), then credit only after a verified `successful_payment` update. Do not run lengthy model analysis inside pre-checkout. Persist/deduplicate Telegram payment charge IDs; Stars refunds use the provider-specific API, not manual receipt handling.
- For live **printing-stage** checkout, establish/revalidate stock and feasible capacity **before collecting payment**; the pre-checkout handler rechecks the payment obligation and current hold if applicable. After verified payment, promote the hold to firm reservation. If stock/capacity fails after funds arrive, do not mark production-ready: hold for audited reschedule, substitution with customer consent, or refund. **Design-only** checkout must not require filament or printer assignment.
- For any evidence-based permitted physical payment, the **owner checks actual settlement**, not just receipts/screenshots. If Stars APIs are implemented, verify the `successful_payment` event and persist its provider charge ID; retain owner verification gate until separately authorized to change policy.

## Launch blocking tests
1. Digital-design products in the Telegram Mini App cannot select bank transfer/manual MMK checkout.
2. A design-stage Stars quote and a physical printing MMK quote remain distinct records and currencies.
3. A simulated payment or test quote cannot turn into a live payment or real job after a feature-flag toggle.
4. A payment callback/bank transfer cannot be double-credited across different orders; wrong buyer/currency/amount/category/refunded payments do not release a stage, and an invoice-opened UI event does not constitute payment.
5. Physical payment evidence alone does not confirm funds; owner audit exists.
6. All payment terms, support, refunds/disputes and taxes are reviewed before accepting money.

## Official Telegram sources
- Digital goods/services and Stars: https://core.telegram.org/bots/payments-stars
- Physical goods/services: https://core.telegram.org/bots/payments
- Mini Apps and launch/authentication: https://core.telegram.org/bots/webapps
