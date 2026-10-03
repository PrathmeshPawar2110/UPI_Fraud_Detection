async function request(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Something went wrong.");
  return data;
}

export const getModelInfo = () => request("/api/model-info");

const post = (path) => (body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const predict = post("/api/predict");
export const checkReceived = post("/api/check-received");
