// Pull UPI payment details out of OCR text from a payment screenshot.
// Tested on Google Pay, PhonePe, Paytm and BHIM receipts (sent and received); bank apps use similar wording.
// Every field is optional: whatever is not found is left for the user to fill in.
//
// `words` are Tesseract words with bounding boxes. The amount is the largest text on every receipt,
// and OCR often drops or garbles it in the plain text, so word height is the most reliable signal.

const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
const MONTH_RE = "(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\.?";

function toNumber(s) {
  const n = parseFloat(String(s).replace(/[,\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

// ---------- app and direction ----------

export function detectApp(text) {
  if (/\bbhim\b/i.test(text)) return "BHIM";
  if (/phone\s?pe/i.test(text)) return "PhonePe";
  if (/google\s*(pay|transaction)|\bg\s?pay\b/i.test(text)) return "Google Pay";
  if (/\bpaytm\b/i.test(text)) return "Paytm";
  return null;
}

// "received" when money came into the user's account, "sent" when it went out.
export function detectDirection(text) {
  if (/money\s+received|received\s+from|credited\s+to|you\s+received|^\s*from\s+[a-z]/im.test(text)) return "received";
  if (/money\s+sent|paid\s+to|sent\s+to|debited\s+from|debited\s+account|\bpaid\b|^\s*to:?\s+[a-z]/im.test(text)) return "sent";
  return null;
}

// ---------- amount ----------

// One amount-shaped word, allowing a leading misread rupee sign (₹ often comes out as Z, I, %, & or ¥).
const AMOUNT_WORD = /^[₹ZzI%&?¥Ff]?((?:[0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]{1,9})(?:\.[0-9]{1,2})?)$/;

function amountFromWords(words) {
  const heights = words.map((w) => w.h).sort((a, b) => a - b);
  const median = heights[Math.floor(heights.length / 2)] || 0;
  const best = words
    .map((w) => ({ ...w, m: w.text.trim().match(AMOUNT_WORD) }))
    .filter((w) => w.m)
    .sort((a, b) => b.h - a.h)[0];
  // Only trust it when it really is the headline number, clearly taller than body text.
  return best && best.h >= median * 1.25 ? toNumber(best.m[1]) : null;
}

const UNITS = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18,
  nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90,
};
const SCALES = { hundred: 100, thousand: 1e3, lakh: 1e5, lakhs: 1e5, crore: 1e7, crores: 1e7 };

// "Rupees Three Hundred Sixty Nine Only" (Paytm) -> 369
function amountFromWordsText(text) {
  const m = text.match(/rupees\s+([a-z\s-]+?)\s+only/i);
  if (!m) return null;
  let total = 0, chunk = 0;
  for (const w of m[1].toLowerCase().split(/[\s-]+/)) {
    if (w in UNITS) chunk += UNITS[w];
    else if (w === "hundred") chunk *= 100;
    else if (w in SCALES) { total += chunk * SCALES[w]; chunk = 0; }
    else if (w !== "and") return null;
  }
  return total + chunk || null;
}

function amountFromText(text) {
  const patterns = [
    /(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)/i,
    /(?:amount|debited|credited)[^0-9\n]{0,20}([0-9][0-9,]*(?:\.[0-9]{1,2})?)/i,
  ];
  for (const p of patterns) {
    const m = text.match(p);
    if (m && toNumber(m[1]) > 0) return toNumber(m[1]);
  }
  // A short number standing on its own line twice, e.g. PhonePe shows the amount at the top and next to the bank.
  const solo = text.match(/^\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?\s*$/gm) || [];
  const counts = {};
  for (const s of solo.map((x) => x.trim())) counts[s] = (counts[s] || 0) + 1;
  const twice = Object.keys(counts).find((k) => counts[k] > 1 && k.replace(/\D/g, "").length <= 9);
  return twice ? toNumber(twice) : null;
}

function findAmount(text, words) {
  const fromWords = amountFromWords(words);
  const inWords = amountFromWordsText(text);
  // The written-out amount (Paytm) is exact; prefer it when the headline number disagrees.
  if (inWords && fromWords !== inWords) return inWords;
  return fromWords ?? amountFromText(text);
}

// ---------- reference ids ----------

function findTxnId(text) {
  const patterns = [
    // the 12-digit UPI reference (UTR / RRN) is the one banks and cybercrime.gov.in ask for
    /(?:utr|rrn|upi\s*(?:ref(?:erence)?|transaction|txn)\s*(?:id|no\.?|number)?)\s*[:\-]?\s*([0-9][0-9 ]{10,16}[0-9])/i,
    /\b([0-9]{12})\b/,
    /(?:transaction|txn|order)\s*id\s*[:\-]?\s*([A-Z0-9]{10,35})/i,
  ];
  for (const p of patterns) {
    const m = text.match(p);
    if (m) return m[1].replace(/\s+/g, "");
  }
  return null;
}

// ---------- counterparty (who paid you, or whom you paid) ----------

const UPI_ID = /([*+•~.\-]*)([a-z0-9][a-z0-9.\-_]*@[a-z][a-z0-9]+)/gi;

function upiIdAfter(text, from) {
  UPI_ID.lastIndex = Math.max(from, 0);
  for (let m; (m = UPI_ID.exec(text));) {
    if (/\.(com|in|org|net)$/i.test(m[2])) continue;
    return (m[1] ? "••••" : "") + m[2].toLowerCase();
  }
  return null;
}

function cleanName(line) {
  const name = line.replace(/\(.*?\)/g, " ").replace(/[^A-Za-z .']/g, " ").replace(/\s+/g, " ").trim();
  const words = name.split(" ").filter((w) => w.length > 1 || /^[A-Z]\.?$/.test(w));
  const out = words.join(" ");
  if (out.length < 3 || !/[a-z]{2}/i.test(out)) return null;
  if (/^(upi|bank|your|account|transfer|details|banking|name|powered|paid|received|from|to)\b/i.test(out)) return null;
  return out;
}

// The first plausible name on the label's own line, or on one of the next few lines.
function nameAfter(text, label) {
  const m = label.exec(text);
  if (!m) return null;
  const rest = text.slice(m.index + m[0].length).split("\n").slice(0, 4);
  for (const line of rest) {
    const name = cleanName(line);
    if (name) return { name, index: m.index };
  }
  return null;
}

function findCounterparty(text, direction) {
  const labels = direction === "received"
    ? [/received\s+from\s*:?/i, /^\s*from\s*:?/im]
    : [/paid\s+to\s*:?/i, /sent\s+to\s*:?/i, /^\s*to\s*:?(?!\s*upi)/im, /banking\s+name\.?\s*:?/i, /payment\s+received\s+by/i];
  for (const label of labels) {
    const hit = nameAfter(text, label);
    if (hit) return { name: hit.name, upi: upiIdAfter(text, hit.index) };
  }
  return { name: null, upi: null };
}

// ---------- status, date, time ----------

function findStatus(text) {
  if (/\b(failed|declined|unsuccessful)\b/i.test(text)) return "Failed";
  if (/\b(pending|processing)\b/i.test(text)) return "Pending";
  if (/\b(success(ful)?|completed|paid|sent|received|credited)\b/i.test(text)) return "Successful";
  return null;
}

function findDateTime(text) {
  let date = null, time = null;
  const year = (y) => (+y < 100 ? 2000 + +y : +y);

  // "16 Jul 2026", "13 Sept 2026", "1st Oct 26"
  let m = text.match(new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?\\s*${MONTH_RE},?\\s*(\\d{4}|\\d{2})\\b`, "i"));
  if (m) date = { y: year(m[3]), mo: MONTHS[m[2].toLowerCase()], d: +m[1] };
  // "Oct 3, 2026"
  if (!date) {
    m = text.match(new RegExp(`\\b${MONTH_RE}\\s*(\\d{1,2})(?:st|nd|rd|th)?,?\\s*(\\d{4})\\b`, "i"));
    if (m) date = { y: +m[3], mo: MONTHS[m[1].toLowerCase()], d: +m[2] };
  }
  // "03/10/2026" or "03-10-26" (Indian apps put the day first)
  if (!date) {
    m = text.match(/\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b/);
    if (m) date = { y: year(m[3]), mo: +m[2] - 1, d: +m[1] };
  }

  // "05:15 PM", "12:25am", "22:45"
  m = text.match(/\b(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?\s*([ap]\.?\s?m\b\.?)?/i);
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

/** words: [{ text, h }] from Tesseract (optional). */
export function parseUpiText(text, words = []) {
  const clean = text.replace(/\r/g, "");
  const direction = detectDirection(clean);
  const party = findCounterparty(clean, direction);
  const { date, time } = findDateTime(clean);
  return {
    app: detectApp(clean),
    direction,
    amount: findAmount(clean, words),
    txnId: findTxnId(clean),
    payee: party.name,
    payeeUpi: party.upi,
    status: findStatus(clean),
    date,
    time,
  };
}
