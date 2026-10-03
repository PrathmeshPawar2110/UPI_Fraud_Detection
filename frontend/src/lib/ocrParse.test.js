// Run with: npm test   (Node's built-in test runner)
// Fixtures mimic real Tesseract output (sparse-text mode) for each app's receipt, including its
// typical OCR noise, with made-up names, IDs and numbers.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseUpiText } from "./ocrParse.js";

// Word heights: the headline amount is much taller than body text, as on every receipt.
const words = (amountText, amountH = 60, bodyH = 26) => [
  { text: amountText, h: amountH },
  ...Array.from({ length: 30 }, (_, i) => ({ text: "word" + i, h: bodyH })),
];

test("Paytm, money received (rupee sign misread as I, amount also in words)", () => {
  const text = `Paytm
Money Received
I369
Rupees Three Hundred Sixty Nine Only
From: Rahul Vijay Mehta
MA
UPI ID: *****¥*0259@ptsbi
To: Asha Kulkarni
UPI ID: asha.kulkarni77@oksbi
Bank account linked to
UPI Ref No: 512345678901
05:15 PM, 16 Jul 2026
Paytm`;
  const p = parseUpiText(text, words("I369"));
  assert.equal(p.app, "Paytm");
  assert.equal(p.direction, "received");
  assert.equal(p.amount, 369);
  assert.equal(p.payee, "Rahul Vijay Mehta");
  assert.equal(p.payeeUpi, "••••0259@ptsbi");
  assert.equal(p.txnId, "512345678901");
  assert.equal(p.status, "Successful");
  assert.deepEqual(p.date, { y: 2026, mo: 6, d: 16 });
  assert.deepEqual(p.time, { h: 17, min: 15 });
});

test("PhonePe, received (dark theme, amount shown twice, noise line before the name)", () => {
  const text = `Transaction Successful
oO
11:09 PM on 13 Sep 2026
Received from
Ir
Neha Patil
300
po +97 eeeee «0700
Neha Sunil Patil ©
Banking Name
Transfer Details
PhonePe Transaction ID
T2609132309192600000001
Credited to
300
J XXXXXX1234
UTR: 498765432109
Powered by`;
  const p = parseUpiText(text, words("300", 31, 28)); // amount barely taller than body text here
  assert.equal(p.app, "PhonePe");
  assert.equal(p.direction, "received");
  assert.equal(p.amount, 300);
  assert.equal(p.payee, "Neha Patil");
  assert.equal(p.txnId, "498765432109", "the 12-digit UTR wins over PhonePe's own ID");
  assert.deepEqual(p.date, { y: 2026, mo: 8, d: 13 });
  assert.deepEqual(p.time, { h: 23, min: 9 });
});

test("Google Pay, sent ('Sept', masked UPI IDs, From: line is the user)", () => {
  const text = `To Kiran Desai
+91 eves 02782
20
© Completed
13 Sept 2026, 8:28 pm
HDFC Bank 0275
UPI transaction ID
612345678909
To: KIRAN ANIL DESAI
++++k226@okicici on Google Pay
From: ASHA KULKARNI (HDFC Bank)
++++54-1@okaxis on Google Pay
Google transaction ID
CICAgAbCdEfGh
G Pay`;
  const p = parseUpiText(text, words("20", 63, 20));
  assert.equal(p.app, "Google Pay");
  assert.equal(p.direction, "sent");
  assert.equal(p.amount, 20);
  assert.equal(p.payee, "Kiran Desai");
  assert.equal(p.payeeUpi, "••••k226@okicici");
  assert.equal(p.txnId, "612345678909");
  assert.equal(p.status, "Successful");
  assert.deepEqual(p.date, { y: 2026, mo: 8, d: 13 });
  assert.deepEqual(p.time, { h: 20, min: 28 });
});

test("BHIM, paid a biller (ordinal date with 2-digit year, 'paytm' inside a UPI ID)", () => {
  const text = `BHIM - Bharat's Own Payments App
& Paid
2824.92
Banking Name.
City Power Ltd
Transaction ID
Date & Time
002554000001 [J
1st Oct 26, 12:25am
To UPI ID
Remarks
paytm
NO REMARK
~53817591@ptybl
Debited account
HDFC BANK CREDIT CARD
XXXXXX36
Payment initiated by ASHA KULKARNI`;
  const p = parseUpiText(text, words("2824.92", 37, 13));
  assert.equal(p.app, "BHIM", "BHIM is detected before Paytm");
  assert.equal(p.direction, "sent");
  assert.equal(p.amount, 2824.92);
  assert.equal(p.payee, "City Power Ltd");
  assert.equal(p.payeeUpi, "••••53817591@ptybl");
  assert.equal(p.txnId, "002554000001");
  assert.deepEqual(p.date, { y: 2026, mo: 9, d: 1 });
  assert.deepEqual(p.time, { h: 0, min: 25 });
});

test("Google Pay received heading 'From Name' (no colon) means received", () => {
  const p = parseUpiText(`From Arjun Rao\n₹1,250\nCompleted\n2 Oct 2026, 9:05 am\nUPI transaction ID\n623456789012`);
  assert.equal(p.direction, "received");
  assert.equal(p.payee, "Arjun Rao");
  assert.equal(p.amount, 1250);
});

test("PhonePe sent: 'Paid to' and 'Debited from'", () => {
  const p = parseUpiText(`Paid to\nRavi Stores\n₹ 450\nDebited from\nXXXXXX9876\nUTR: 634567890123\n10:42 am on 2 Oct 2026`);
  assert.equal(p.app, null);
  assert.equal(p.direction, "sent");
  assert.equal(p.payee, "Ravi Stores");
  assert.equal(p.amount, 450);
  assert.deepEqual(p.time, { h: 10, min: 42 });
});

test("failed payment and Indian digit grouping", () => {
  const p = parseUpiText(`Payment failed\nPaid to Meera Iyer\nRs. 1,25,000.50\n03/10/2026 22:45`);
  assert.equal(p.status, "Failed");
  assert.equal(p.amount, 125000.5);
  assert.deepEqual(p.date, { y: 2026, mo: 9, d: 3 });
  assert.deepEqual(p.time, { h: 22, min: 45 });
});

test("nothing recognisable gives nulls, not guesses", () => {
  const p = parseUpiText("hello world");
  for (const k of ["app", "direction", "amount", "txnId", "payee", "payeeUpi", "status", "date", "time"]) {
    assert.equal(p[k], null, k);
  }
});
