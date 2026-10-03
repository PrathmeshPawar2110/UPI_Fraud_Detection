"""UPI Guard: FastAPI backend.

Run (from backend/):  uvicorn app.main:app --reload --reload-dir app --port 8000
API docs:             http://127.0.0.1:8000/docs

The original endpoints (/api/predict, /api/check-received, /api/model-info) are unchanged and need no
account. Everything that stores data lives in app/routes and requires a signed-in user.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .auth import router as auth_router
from .db import init_db
from .fraud import META, score
from .received import check_received
from .routes import account, ai, alerts, cases, intel, network, simulator, transactions
from .schemas import Prediction, ReceivedPayment, Transaction


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="UPI Guard API", lifespan=lifespan)

# The Vite dev server proxies /api, but allow direct calls from it too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
}


# Same policy as vercel.json (keep in sync). OCR needs the jsDelivr worker/core, WebAssembly and the
# tessdata language files; React's style attributes need 'unsafe-inline' styles; no inline scripts.
CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net blob:; "
       "worker-src 'self' blob:; connect-src 'self' data: https://cdn.jsdelivr.net https://tessdata.projectnaptha.com; "
       "img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")


@app.middleware("http")
async def limits_and_headers(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > config.MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request is too large."})
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    elif request.url.path not in ("/docs", "/redoc"):  # Swagger UI loads its own CDN assets
        response.headers.setdefault("Content-Security-Policy", CSP)
    return response


FIELD_LABELS = {
    "type": "Payment type",
    "amount": "Amount",
    "hour": "Hour",
    "sender_balance_before": "Sender's balance before",
    "sender_balance_after": "Sender's balance after",
    "receiver_balance_before": "Receiver's balance before",
    "receiver_balance_after": "Receiver's balance after",
    "knows_sender": "Do you know the sender",
    "in_bank": "Does it show in your bank",
    "asked_to_pay": "Asked to send money back or pay",
}


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Return one readable message, e.g. "Amount: must be more than zero."."""
    err = exc.errors()[0]
    field = next((p for p in reversed(err["loc"]) if p in FIELD_LABELS), None)
    msg = err["msg"].removeprefix("Value error, ")
    if field == "type":
        msg = "Payment type must be a transfer or a cash withdrawal."
    elif field:
        msg = f"{FIELD_LABELS[field]}: {msg[0].lower() + msg[1:]}."
    else:
        name = next((p for p in reversed(err["loc"]) if isinstance(p, str) and p not in ("body", "query", "path")), None)
        if name:
            msg = f"{name.replace('_', ' ').capitalize()}: {msg[0].lower() + msg[1:]}."
    return JSONResponse(status_code=400, content={"detail": msg})


@app.get("/api/model-info")
def model_info():
    keys = ["dataset", "split", "thresholds", "metrics_test", "feature_importance", "samples"]
    return {k: META[k] for k in keys}


@app.post("/api/predict", response_model=Prediction)
def predict(t: Transaction):
    return score(t)


@app.post("/api/check-received", response_model=Prediction)
def check_received_payment(p: ReceivedPayment):
    """Money received into the user's account: rule-based, since the model only learned outgoing fraud."""
    return check_received(p)


for r in (auth_router, transactions.router, intel.router, cases.router, alerts.router, network.router,
          simulator.router, ai.router, account.router):
    app.include_router(r)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str):
    return JSONResponse(status_code=404, content={"detail": "Not found."})


# Serve the built React app (frontend/dist) when it exists, so one process can run everything.
# Unknown paths fall back to index.html so client-side routes like /transactions work on reload.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = (DIST / path).resolve()
        if path and file.is_file() and DIST in file.parents:
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
