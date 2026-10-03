"""UPI Fraud Check: FastAPI backend.

Run (from backend/):  uvicorn app.main:app --reload --port 8000
API docs:             http://127.0.0.1:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .fraud import META, score
from .schemas import Prediction, Transaction

app = FastAPI(title="UPI Fraud Check API")

# The Vite dev server proxies /api, but allow direct calls from it too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FIELD_LABELS = {
    "type": "Payment type",
    "amount": "Amount",
    "hour": "Hour",
    "sender_balance_before": "Sender's balance before",
    "sender_balance_after": "Sender's balance after",
    "receiver_balance_before": "Receiver's balance before",
    "receiver_balance_after": "Receiver's balance after",
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
    return JSONResponse(status_code=400, content={"detail": msg})


@app.get("/api/model-info")
def model_info():
    keys = ["dataset", "split", "thresholds", "metrics_test", "feature_importance", "samples"]
    return {k: META[k] for k in keys}


@app.post("/api/predict", response_model=Prediction)
def predict(t: Transaction):
    return score(t)


# Serve the built React app (frontend/dist) when it exists, so one process can run everything.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
