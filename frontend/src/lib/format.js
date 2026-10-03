export const inr = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });

export const pad = (n) => String(n).padStart(2, "0");

/** Value for a datetime-local input. */
export const localDateTime = (d = new Date(), h = d.getHours(), min = d.getMinutes()) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(h)}:${pad(min)}`;

/** "03 Oct 2026 · 12:48 AM" */
export const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }).toUpperCase();
  return `${date} · ${time}`;
};

export const party = (t) => t.counterparty_upi || t.counterparty_name || "Unknown";

export const DIRECTION = { sent: "Sent", received: "Received", cash_out: "Cash withdrawal" };

export const downloadJson = (data, name) => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
