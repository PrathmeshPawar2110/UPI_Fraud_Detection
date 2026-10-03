// Pull UPI payment details out of OCR text from a payment screenshot
// (Google Pay, PhonePe, Paytm, BHIM and most bank apps use similar wording).
// Every field is optional: whatever is not found is left for the user to fill in.

const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };

function toNumber(s) {
  const n = parseFloat(String(s).replace(/[,\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function findAmount(text) {
  // OCR often reads the rupee sign as "%", "Z", "2" or "&", so try explicit markers first.
  const patterns = [
    /(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)/i,
    /(?:amount|paid|sent|debited|received)[^0-9\n]{0,20}([0-9][0-9,]*(?:\.[0-9]{1,2})?)/i,
    /^[%Z&?]\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*$/m,
  ];
  for (const p of patterns) {
    const m = text.match(p);
    if (m) {
      const n = toNumber(m[1]);
      if (n && n > 0) return n;
    }
  }
  // Fallback: a line that is only a number with Indian comma grouping, e.g. "1,250" or "12,500.00"
  const m = text.match(/^\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?)\s*$/m);
  return m ? toNumber(m[1]) : null;
}

function findTxnId(text) {
  const patterns = [
    /(?:upi\s*(?:transaction|txn|ref(?:erence)?)\s*(?:id|no\.?|number)?|utr(?:\s*no\.?)?|rrn)\s*[:\-]?\s*([0-9][0-9 ]{10,16}[0-9])/i,
    /(?:transaction|txn|order)\s*id\s*[:\-]?\s*([A-Z0-9]{10,35})/i,
    /\b([0-9]{12})\b/,
  ];
  for (const p of patterns) {
    const m = text.match(p);
    if (m) return m[1].replace(/\s+/g, "");
  }
  return null;
}

function findUpiIds(text) {
  const ids = text.match(/[a-z0-9][a-z0-9.\-_]{1,}@[a-z][a-z0-9]{1,}/gi) || [];
  return [...new Set(ids.map((s) => s.toLowerCase()))].filter((s) => !/\.(com|in|org|net)$/.test(s));
}

function findPayee(text) {
  const m = text.match(/(?:paid\s+to|sent\s+to|to)\s*[:\-]?\s*\n?\s*([A-Za-z][A-Za-z .']{2,40})/i);
  if (!m) return null;
  const name = m[1].trim().split("\n")[0].trim();
  return /^(your|bank|upi|account)/i.test(name) ? null : name;
}

function findStatus(text) {
  if (/\b(failed|declined|unsuccessful)\b/i.test(text)) return "Failed";
  if (/\b(pending|processing)\b/i.test(text)) return "Pending";
  if (/\b(success(ful)?|completed|paid|sent)\b/i.test(text)) return "Successful";
  return null;
}

function findDateTime(text) {
  let date = null, time = null;

  // "3 Oct 2026", "03 October, 2026", "Oct 3, 2026"
  let m = text.match(/\b(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*(\d{4})/i);
  if (m) date = { y: +m[3], mo: MONTHS[m[2].toLowerCase()], d: +m[1] };
  if (!date) {
    m = text.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{1,2}),?\s*(\d{4})/i);
    if (m) date = { y: +m[3], mo: MONTHS[m[1].toLowerCase()], d: +m[2] };
  }
  // "03/10/2026" or "03-10-26" (Indian apps use day first)
  if (!date) {
    m = text.match(/\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b/);
    if (m) {
      const y = +m[3] < 100 ? 2000 + +m[3] : +m[3];
      date = { y, mo: +m[2] - 1, d: +m[1] };
    }
  }

  // "10:45 pm", "10:45PM", "22:45"
  m = text.match(/\b(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?\s*([ap]\.?m\.?)?/i);
  if (m) {
    let h = +m[1];
    const min = +m[2];
    const ampm = m[3] ? m[3].toLowerCase()[0] : null;
    if (ampm === "p" && h < 12) h += 12;
    if (ampm === "a" && h === 12) h = 0;
    if (h < 24 && min < 60) time = { h, min };
  }
  return { date, time };
}

export function parseUpiText(text) {
  const clean = text.replace(/\r/g, "");
  const upiIds = findUpiIds(clean);
  const { date, time } = findDateTime(clean);
  return {
    amount: findAmount(clean),
    txnId: findTxnId(clean),
    payee: findPayee(clean),
    payeeUpi: upiIds[0] || null,
    payerUpi: upiIds[1] || null,
    status: findStatus(clean),
    date,
    time,
  };
}
