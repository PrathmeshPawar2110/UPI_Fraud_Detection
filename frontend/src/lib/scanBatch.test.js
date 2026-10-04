import { test } from "node:test";
import assert from "node:assert/strict";
import { missingFor, toTransaction } from "./scanBatch.js";

const NOW = new Date(2026, 9, 4, 15, 30);

test("full receipt becomes a saveable transaction", () => {
  const tx = toTransaction({ app: "Google Pay", direction: "sent", amount: 20, txnId: "612345678909",
    payee: "Kiran Desai", payeeUpi: "kiran.d@okicici", status: "Successful",
    date: { y: 2026, mo: 8, d: 13 }, time: { h: 20, min: 28 } }, NOW);
  assert.deepEqual(tx, { occurred_at: "2026-09-13T20:28", direction: "sent", amount: 20, counterparty_name: "Kiran Desai",
    counterparty_upi: "kiran.d@okicici", external_id: "612345678909", status: "success", payment_app: "Google Pay",
    source: "screenshot" });
});

test("masked UPI IDs, odd references and missing date/time are handled", () => {
  const tx = toTransaction({ direction: "received", amount: 300, payeeUpi: "••••0259@ptsbi", txnId: "T26 09 13!",
    payee: "Neha Patil" }, NOW);
  assert.equal(tx.counterparty_upi, null);
  assert.equal(tx.external_id, null);
  assert.equal(tx.direction, "received");
  assert.equal(tx.occurred_at, "2026-10-04T12:00"); // today, noon when the time wasn't read
});

test("missing fields are reported", () => {
  assert.deepEqual(missingFor({ amount: 5, direction: "sent" }), []);
  assert.deepEqual(missingFor({ direction: "sent" }), ["amount"]);
  assert.deepEqual(missingFor({}), ["amount", "sent or received"]);
});
