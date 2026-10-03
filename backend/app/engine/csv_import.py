"""CSV transaction import.

Required columns: a date/time, a direction and an amount. Column names are matched loosely
(e.g. "date", "timestamp", "txn date"; "type", "dr/cr"; "amount (inr)"). Unknown columns are ignored.
Bad rows are skipped and reported; good rows are imported.
"""

import csv
import io
import re
from datetime import datetime

from pydantic import ValidationError

from ..routes.common import TransactionIn

ALIASES = {
    "occurred_at": ["timestamp", "datetime", "date time", "date", "txn date", "transaction date", "time", "occurred at"],
    "direction": ["direction", "type", "dr/cr", "debit/credit", "cr/dr", "txn type", "transaction type"],
    "amount": ["amount", "amount (inr)", "amount inr", "value", "txn amount"],
    "counterparty_name": ["name", "counterparty", "counterparty name", "payee", "payer", "to/from", "party", "merchant"],
    "counterparty_upi": ["upi", "upi id", "vpa", "counterparty upi", "upi_id"],
    "payment_app": ["app", "payment app", "payment_app"],
    "status": ["status"],
    "external_id": ["reference", "ref", "utr", "upi ref", "ref no", "transaction id", "txn id", "external id"],
    "balance_before": ["balance before", "opening balance", "balance_before"],
    "balance_after": ["balance after", "closing balance", "balance", "balance_after"],
    "category": ["category"],
    "note": ["note", "remarks", "description", "narration"],
    "device_id": ["device", "device id", "device_id"],
    "location": ["location", "city"],
}
DIRECTIONS = {
    "sent": "sent", "debit": "sent", "dr": "sent", "paid": "sent", "out": "sent", "send": "sent",
    "received": "received", "credit": "received", "cr": "received", "in": "received", "receive": "received",
    "cash_out": "cash_out", "cash out": "cash_out", "withdrawal": "cash_out", "atm": "cash_out",
}
STATUSES = {"success": "success", "successful": "success", "completed": "success", "failed": "failed",
            "failure": "failed", "pending": "pending", "processing": "pending"}
DATE_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
                "%d-%m-%Y", "%d %b %Y %H:%M", "%d %b %Y, %I:%M %p", "%d %b %Y %I:%M %p", "%d %b %Y",
                "%d/%m/%Y %I:%M %p", "%d-%m-%Y %I:%M %p"]


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower().replace("_", " "))


def parse_date(s: str) -> datetime:
    s = re.sub(r"\s+", " ", s.strip())
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    raise ValueError(f"unrecognised date/time '{s}' (use YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM)")


def _number(s: str) -> float | None:
    s = (s or "").replace(",", "").replace("₹", "").replace("INR", "").strip()
    return float(s) if s else None


def parse(text: str, max_rows: int) -> tuple[list[TransactionIn], list[dict]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise ValueError("The file is empty.")
    columns = {}
    for field, names in ALIASES.items():
        for h in reader.fieldnames:
            if _norm(h) in names:
                columns[field] = h
                break
    missing = [f for f in ("occurred_at", "direction", "amount") if f not in columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(
            {"occurred_at": "date/time", "direction": "direction (sent/received)", "amount": "amount"}[m] for m in missing))

    rows, errors = [], []
    for line, raw in enumerate(reader, start=2):
        if len(rows) + len(errors) >= max_rows:
            errors.append({"line": line, "error": f"Stopped after {max_rows} rows."})
            break
        try:
            get = lambda f: (raw.get(columns[f]) or "").strip() if f in columns else ""
            direction = DIRECTIONS.get(get("direction").lower())
            if not direction:
                raise ValueError(f"direction '{get('direction')}' should be sent/received/cash_out (or debit/credit)")
            data = {
                "occurred_at": parse_date(get("occurred_at")),
                "direction": direction,
                "amount": _number(get("amount")),
                "status": STATUSES.get(get("status").lower(), "success"),
                "source": "csv",
            }
            for f in ("counterparty_name", "counterparty_upi", "payment_app", "external_id", "category",
                      "note", "device_id", "location"):
                if get(f):
                    data[f] = get(f)
            for f in ("balance_before", "balance_after"):
                if get(f):
                    data[f] = _number(get(f))
            if data["amount"] is None:
                raise ValueError("amount is empty")
            rows.append(TransactionIn(**data))
        except ValidationError as e:
            err = e.errors()[0]
            errors.append({"line": line, "error": f"{'.'.join(map(str, err['loc']))}: {err['msg'].removeprefix('Value error, ')}"})
        except ValueError as e:
            errors.append({"line": line, "error": str(e)})
    return rows, errors
