"""Transaction history import: CSV, Excel (.xlsx / .xls) and bank-statement layouts.

Needs a date and an amount, plus a way to tell money out from money in: a direction column
("type", "dr/cr"…), separate debit / credit (withdrawal / deposit) columns, or a signed amount
("-500", "500 Dr"). Column names are matched loosely and unknown columns are ignored. Account details
above the table are skipped: the header is the first row (of the first 40) that names the needed
columns. Bad rows are skipped and reported; blank and summary rows (no date and no amount) are
ignored. UPI IDs and 12-digit UPI references are picked out of the narration when there's no column
for them, and the balance before a payment is worked out from a running "balance" column, so the
model can score statement rows.
"""

import csv
import io
import re
import zipfile
from datetime import date, datetime, time
from html.parser import HTMLParser

from pydantic import ValidationError

from ..routes.common import TransactionIn

ALIASES = {
    "occurred_at": ["timestamp", "datetime", "date time", "date & time", "date", "txn date", "transaction date",
                    "tran date", "value date", "value dt", "posting date", "occurred at"],
    "time": ["time", "txn time", "transaction time"],
    "direction": ["direction", "type", "dr/cr", "debit/credit", "cr/dr", "dr / cr", "txn type", "transaction type"],
    "amount": ["amount", "amount (inr)", "amount inr", "amount(inr)", "amount (rs.)", "amount(rs.)", "value",
               "txn amount", "transaction amount"],
    "debit": ["debit", "debit amount", "debit amt", "debit (inr)", "debit(inr)", "withdrawal", "withdrawals",
              "withdrawal amt.", "withdrawal amt", "withdrawal amount", "withdrawal (dr)", "dr amount", "paid out"],
    "credit": ["credit", "credit amount", "credit amt", "credit (inr)", "credit(inr)", "deposit", "deposits",
               "deposit amt.", "deposit amt", "deposit amount", "deposit (cr)", "cr amount", "paid in"],
    "counterparty_name": ["name", "counterparty", "counterparty name", "payee", "payer", "to/from", "party", "merchant",
                          "transaction details", "details", "beneficiary"],
    "counterparty_upi": ["upi", "upi id", "vpa", "counterparty upi", "upi_id"],
    "payment_app": ["app", "payment app", "payment_app"],
    "status": ["status"],
    "external_id": ["reference", "ref", "utr", "upi ref", "upi ref no.", "upi ref no", "ref no", "ref no.",
                    "chq./ref.no.", "chq/ref no", "chq / ref no.", "ref no./cheque no.", "transaction id", "txn id",
                    "external id", "rrn"],
    "balance_before": ["balance before", "opening balance", "balance_before"],
    "balance_after": ["balance after", "closing balance", "balance", "balance_after", "balance (inr)", "balance(inr)"],
    "category": ["category", "tags"],
    "note": ["note", "remarks", "description", "narration", "particulars", "comment"],
    "device_id": ["device", "device id", "device_id"],
    "location": ["location", "city"],
}
DIRECTIONS = {
    "sent": "sent", "debit": "sent", "dr": "sent", "paid": "sent", "out": "sent", "send": "sent", "d": "sent",
    "received": "received", "credit": "received", "cr": "received", "in": "received", "receive": "received", "c": "received",
    "cash_out": "cash_out", "cash out": "cash_out", "withdrawal": "cash_out", "atm": "cash_out",
}
STATUSES = {"success": "success", "successful": "success", "completed": "success", "failed": "failed",
            "failure": "failed", "pending": "pending", "processing": "pending"}
DATE_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d",
                "%Y-%m-%d %I:%M %p", "%Y/%m/%d %H:%M", "%Y/%m/%d",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m/%Y %I:%M %p", "%d/%m/%Y %I:%M:%S %p",
                "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d-%m-%Y %I:%M %p",
                "%d/%m/%y %H:%M", "%d/%m/%y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y",
                "%d %b %Y %H:%M", "%d %b %Y %H:%M:%S", "%d %b %Y, %I:%M %p", "%d %b %Y %I:%M %p", "%d %b %Y",
                "%d %b %y", "%d-%b-%Y", "%d-%b-%y", "%d-%b-%Y %H:%M", "%d %B %Y", "%d %B %Y %I:%M %p",
                "%b %d, %Y", "%b %d, %Y %I:%M %p", "%B %d, %Y"]
TIME_FORMATS = ["%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%I:%M%p"]
HEADER_SCAN = 40
MAX_UNZIPPED = 60_000_000
VPA = re.compile(r"(?<![\w.@])([a-z0-9][a-z0-9._]{1,255}@[a-z][a-z0-9]{1,63})(?![\w@]|\.[a-z])", re.I)  # not emails
UPI_REF = re.compile(r"(?<!\d)(\d{12})(?!\d)")
PARTY_PREFIX = re.compile(r"^(paid to|sent to|money sent to|transfer to|received from|money received from|"
                          r"payment from|payment to)\s+", re.I)


def _norm(h) -> str:
    h = re.sub(r"\s+", " ", str(h or "").strip().lower().replace("_", " "))
    h = re.sub(r"\(\s*(.*?)\s*\)", r"(\1)", h)  # "amount (inr )" -> "amount (inr)"
    return re.sub(r"\s*\((inr|rs\.?|₹)\)$", "", h)  # "withdrawal amount (inr)" -> "withdrawal amount"


def parse_date(s: str) -> datetime:
    s = re.sub(r"\s+", " ", s.strip())
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    raise ValueError(f"unrecognised date/time '{s}' (use YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM)")


def _time(s: str) -> time | None:
    s = re.sub(r"\s+", " ", s.strip()).upper()
    for f in TIME_FORMATS:
        try:
            return datetime.strptime(s, f).time()
        except ValueError:
            continue
    return None


def _number(s: str) -> float | None:
    s = re.sub(r"(?i)₹|inr|rs\.?|\s", "", s or "").replace(",", "")
    return float(s) if s else None


def _signed(s: str) -> tuple[float | None, str | None]:
    """'-500', '(500)', '500 Dr', '+ ₹500', '500.00 CR' -> (amount, direction or None)."""
    s = (s or "").strip()
    if not s:
        return None, None
    direction = None
    m = re.search(r"(?i)\s*\b(dr|cr)\.?$", s)
    if m:
        direction = "sent" if m.group(1).lower() == "dr" else "received"
        s = s[:m.start()]
    if s.startswith("(") and s.endswith(")"):
        s, direction = s[1:-1], direction or "sent"
    s = s.strip()
    if s[:1] in "+-":
        direction = direction or ("sent" if s[0] == "-" else "received")
        s = s[1:]
    value = _number(s)
    return (abs(value) if value is not None else None), direction


# ---------- reading files into rows of strings ----------

def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _xlsx_rows(data: bytes, limit: int) -> list[list[str]]:
    from openpyxl import load_workbook
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:  # refuse zip bombs before parsing any XML
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise ValueError("This Excel file is too large. Export fewer rows or save it as .csv.")
    except zipfile.BadZipFile as e:
        raise ValueError("Couldn't open this Excel file. Save it again as .xlsx or .csv and retry.") from e
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise ValueError("Couldn't open this Excel file. Save it again as .xlsx or .csv and retry.") from e
    try:
        for ws in wb.worksheets:  # first sheet that has something in it
            rows = []
            for r in ws.iter_rows(values_only=True):
                rows.append([_cell(v) for v in r])
                if len(rows) >= limit:
                    break
            if any(any(c for c in r) for r in rows):
                return rows
        return []
    finally:
        wb.close()


def _xls_rows(data: bytes, limit: int) -> list[list[str]]:
    import xlrd
    try:
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
    except xlrd.XLRDError as e:
        raise ValueError("Couldn't open this .xls file. Save it again as .xlsx or .csv and retry.") from e
    for sheet in book.sheets():
        rows = []
        for i in range(min(sheet.nrows, limit)):
            row = []
            for c in sheet.row(i):
                if c.ctype == xlrd.XL_CELL_DATE:
                    try:
                        row.append(_cell(xlrd.xldate_as_datetime(c.value, book.datemode)))
                    except (ValueError, OverflowError):
                        row.append("")
                else:
                    row.append(_cell(c.value))
            rows.append(row)
        if any(any(c for c in r) for r in rows):
            return rows
    return []


class _Table(HTMLParser):
    """Some banks' ".xls" downloads are really an HTML table."""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if data[:2] not in (b"\xff\xfe", b"\xfe\xff") else ("utf-16",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1252", errors="replace")


def text_rows(text: str, limit: int) -> list[list[str]]:
    text = text.lstrip("﻿")
    if re.match(r"\s*<", text) and re.search(r"(?i)<t[dr]\b", text[:200_000]):
        t = _Table()
        t.feed(text)
        return t.rows[:limit]
    sample = "\n".join(text.splitlines()[:HEADER_SCAN])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for r in csv.reader(io.StringIO(text), dialect):
        rows.append(r)
        if len(rows) >= limit:
            break
    return rows


def read_file(name: str, data: bytes, max_rows: int) -> list[list[str]]:
    limit = max_rows + HEADER_SCAN + 1
    if data[:4] == b"PK\x03\x04":  # .xlsx is a zip
        return _xlsx_rows(data, limit)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # legacy .xls (OLE2)
        return _xls_rows(data, limit)
    if re.search(r"(?i)\.(xlsx|xlsm|xls|ods)$", name or "") and not re.match(rb"\s*<", data[:512]):
        if (name or "").lower().endswith(".ods"):
            raise ValueError("OpenDocument (.ods) files aren't supported. Save it as .xlsx or .csv.")
        raise ValueError("This doesn't look like a real Excel file. Save it again as .xlsx or .csv and retry.")
    return text_rows(_text(data), limit)


# ---------- turning rows into transactions ----------

def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    best = None
    for i, row in enumerate(rows[:HEADER_SCAN]):
        names = [_norm(h) for h in row]
        cols = {}
        for field, aliases in ALIASES.items():
            for alias in aliases:  # alias order wins over column order ("date" before "value date")
                if alias in names and names.index(alias) not in cols.values():
                    cols[field] = names.index(alias)
                    break
        has_amount = "amount" in cols or "debit" in cols or "credit" in cols
        if "occurred_at" in cols and has_amount:
            return i, cols
        if best is None and len(cols) >= 2:
            best = (i, cols)
    i, cols = best or (0, {})
    missing = []
    if "occurred_at" not in cols:
        missing.append("date")
    if not ({"amount", "debit", "credit"} & cols.keys()):
        missing.append("amount (or debit / credit columns)")
    raise ValueError("Missing required column(s): " + ", ".join(missing)
                     + ". The first row of the table should have column names like Date, Amount, Debit, Credit.")


def parse_rows(rows: list[list[str]], max_rows: int) -> tuple[list[TransactionIn], list[dict]]:
    if not rows or not any(any(str(c).strip() for c in r) for r in rows):
        raise ValueError("The file is empty.")
    head, cols = _find_header(rows)
    out, errors = [], []
    for line, raw in enumerate(rows[head + 1:], start=head + 2):
        get = lambda f: (str(raw[cols[f]]) if f in cols and cols[f] < len(raw) else "").strip()
        if not any(str(c).strip() for c in raw):
            continue
        if not (get("amount") or get("debit") or get("credit")):
            continue  # opening/closing balance lines, totals, footers
        if len(out) + len(errors) >= max_rows:
            errors.append({"line": line, "error": f"Stopped after {max_rows} rows."})
            break
        try:
            out.append(TransactionIn(**_row(get)))
        except ValidationError as e:
            err = e.errors()[0]
            errors.append({"line": line, "error": f"{'.'.join(map(str, err['loc']))}: {err['msg'].removeprefix('Value error, ')}"})
        except ValueError as e:
            msg = str(e)
            if msg.startswith("could not convert string to float"):
                msg = f"amount '{msg.split(': ', 1)[-1].strip(chr(39))}' is not a number"
            errors.append({"line": line, "error": msg})
    if not out and not errors:
        raise ValueError("No payments found under the column names.")
    return out, errors


def _row(get) -> dict:
    occurred = parse_date(get("occurred_at"))
    if get("time") and occurred.time() == time(0, 0):
        t = _time(get("time"))
        if t:
            occurred = datetime.combine(occurred.date(), t)

    text = " ".join(filter(None, [get("counterparty_name"), get("note")]))
    amount, direction = None, DIRECTIONS.get(get("direction").lower().strip(". "))
    debit, credit = _number(get("debit")), _number(get("credit"))
    if debit or credit:
        if debit and credit:
            raise ValueError("both debit and credit are filled in")
        amount, side = (abs(debit), "sent") if debit else (abs(credit), "received")
        direction = direction if direction == "cash_out" and side == "sent" else side
    else:
        amount, signed_dir = _signed(get("amount"))
        direction = direction or signed_dir
    if amount is None:
        raise ValueError("amount is empty")
    if not direction:
        m = PARTY_PREFIX.match(get("counterparty_name"))
        if m:
            direction = "received" if "from" in m.group(1).lower() else "sent"
    if not direction:
        raise ValueError(f"can't tell if money went out or came in (direction '{get('direction')}'); "
                         "add a sent/received column, debit/credit columns, or a signed amount")

    data = {"occurred_at": occurred, "direction": direction, "amount": amount,
            "status": STATUSES.get(get("status").lower(), "success"), "source": "csv"}
    for f in ("payment_app", "external_id", "category", "device_id", "location"):
        if get(f):
            data[f] = get(f)
    name = PARTY_PREFIX.sub("", get("counterparty_name"))
    upi = get("counterparty_upi") or (m.group(1) if (m := VPA.search(text)) else "")
    if upi:
        data["counterparty_upi"] = upi.lower()
    if name and not VPA.fullmatch(name):
        data["counterparty_name"] = name[:120]
    if get("note"):
        data["note"] = get("note")[:280]
    if "external_id" not in data and (m := UPI_REF.search(text)):
        data["external_id"] = m.group(1)
    for f in ("balance_before", "balance_after"):
        if get(f):
            value, _ = _signed(get(f))
            if value is not None:
                data[f] = value
    # Statements give the running balance after each line; the model needs the balance before it.
    if "balance_before" not in data and "balance_after" in data and direction in ("sent", "cash_out", "received"):
        before = data["balance_after"] + (amount if direction != "received" else -amount)
        if before >= 0:
            data["balance_before"] = round(before, 2)
    return data


def parse(text: str, max_rows: int) -> tuple[list[TransactionIn], list[dict]]:
    return parse_rows(text_rows(text, max_rows + HEADER_SCAN + 1), max_rows)


def parse_file(name: str, data: bytes, max_rows: int) -> tuple[list[TransactionIn], list[dict]]:
    return parse_rows(read_file(name, data, max_rows), max_rows)
