// Turn a parsed screenshot (ocrParse.js) into a transaction for POST /api/transactions/batch.
import { localDateTime } from "./format.js";

const STATUS = { Successful: "success", Failed: "failed", Pending: "pending" };
const VPA = /^[a-z0-9][a-z0-9._-]{1,255}@[a-z][a-z0-9]{1,63}$/i;
const REF = /^[A-Za-z0-9-]{4,64}$/;

/** What's missing before a scan can be saved, or [] if it's ready. */
export function missingFor(p) {
  const out = [];
  if (!p?.amount) out.push("amount");
  if (!p?.direction) out.push("sent or received");
  return out;
}

/**
 * Build the transaction payload. Balances aren't on receipts, so the ML model can't score these until a
 * balance is added; history patterns, rules and community reports still apply.
 * `now` is injectable for tests.
 */
export function toTransaction(p, now = new Date()) {
  const d = p.date ? new Date(p.date.y, p.date.mo, p.date.d) : now;
  const t = p.time || { h: 12, min: 0 };
  // Masked receipt IDs ("••••0259@ptsbi") aren't full UPI IDs: keep only real ones.
  const upi = p.payeeUpi && !p.payeeUpi.startsWith("•") && VPA.test(p.payeeUpi) ? p.payeeUpi.toLowerCase() : null;
  return {
    occurred_at: localDateTime(d, t.h, t.min),
    direction: p.direction === "received" ? "received" : "sent",
    amount: p.amount,
    counterparty_name: p.payee || null,
    counterparty_upi: upi,
    external_id: p.txnId && REF.test(p.txnId) ? p.txnId : null,
    status: STATUS[p.status] || "success",
    payment_app: p.app || null,
    source: "screenshot",
  };
}
