export const inr = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });

export const pad = (n) => String(n).padStart(2, "0");

/** Value for a datetime-local input. */
export const localDateTime = (d = new Date(), h = d.getHours(), min = d.getMinutes()) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(h)}:${pad(min)}`;
