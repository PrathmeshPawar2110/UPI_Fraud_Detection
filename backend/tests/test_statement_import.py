"""Statement upload: CSV / Excel / bank layouts, duplicates, flagged results and file safety."""

import io
import zipfile
from datetime import datetime

import pytest
from openpyxl import Workbook

from app.engine import csv_import

MAX = 2000


def xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, data: bytes, name: str):
    return client.post("/api/transactions/import-file", params={"name": name}, content=data,
                       headers={"Content-Type": "application/octet-stream"})


# A bank-style Excel statement: account details above the table, separate withdrawal / deposit
# columns, a running closing balance, and UPI details only inside the narration.
BANK = [
    ["XYZ Bank Ltd"], ["Account No", "XXXX1234"], ["Statement from 01/09/2026 to 05/09/2026"], [],
    ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
    [datetime(2026, 9, 1, 10, 5), "UPI-CHAI POINT-chaipoint.ka@ybl-YESB0000001-412345678901-UPI", "", "01/09/26", 240, None, 41760],
    [datetime(2026, 9, 1, 19, 40), "UPI-FRESH MART-freshmart.blr@okaxis-UTIB0000001-412345678902-UPI", "", "01/09/26", 1200, None, 40560],
    [datetime(2026, 9, 2, 9, 0), "NEFT-EMPLOYER PAYROLL", "N123", "02/09/26", None, 62000, 102560],
    [datetime(2026, 9, 3, 2, 10), "UPI-QUICK PAY-quickpay.mule01@axl-412345678903-UPI", "", "03/09/26", 102560, None, 0],
    [], ["Opening Balance", "", "", "", "", "", 42000], ["**End of statement**"],
]


def test_bank_excel_statement(user):
    r = upload(user, xlsx(BANK), "statement.xlsx")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 4 and body["errors"] == [] and body["duplicates"] == 0
    items = user.get("/api/transactions", params={"sort": "oldest"}).json()["items"]
    assert [t["direction"] for t in items] == ["sent", "sent", "received", "sent"]
    first, drain = items[0], items[3]
    assert first["counterparty_upi"] == "chaipoint.ka@ybl" and first["external_id"] == "412345678901"
    assert first["balance_before"] == 42000  # worked out from the closing balance
    assert drain["occurred_at"].startswith("2026-09-03T02:10")
    # the drain at 2 a.m. to a new payee is flagged, and listed first
    assert body["flagged"] and body["flagged"][0]["counterparty_upi"] == "quickpay.mule01@axl"
    assert body["flagged"][0]["risk_level"] == "high" and body["high_risk"] >= 1


def test_uploading_the_same_statement_twice_adds_nothing(user):
    data = xlsx(BANK)
    assert upload(user, data, "s.xlsx").json()["imported"] == 4
    again = upload(user, data, "s.xlsx").json()
    assert again["imported"] == 0 and again["duplicates"] == 4
    assert user.get("/api/transactions").json()["total"] == 4


def test_overlapping_statement_only_adds_new_rows(user):
    upload(user, xlsx(BANK[:7]), "aug.xlsx")  # first two payments
    r = upload(user, xlsx(BANK), "sep.xlsx").json()
    assert r["imported"] == 2 and r["duplicates"] == 2


def test_signed_amounts_and_separate_time_column():
    text = ("Date,Time,Transaction Details,UPI Ref No.,Amount\n"
            "05 Sep 2026,07:15 PM,Paid to Ravi Auto,512345678904,-160\n"
            "06 Sep 2026,10:02 AM,Received from Asha K,512345678905,\"+1,500\"\n"
            "07 Sep 2026,11:00 AM,Paid to Store,,500 Dr\n")
    rows, errors = csv_import.parse(text, MAX)
    assert errors == []
    assert [(r.direction, r.amount) for r in rows] == [("sent", 160), ("received", 1500), ("sent", 500)]
    assert rows[0].occurred_at == datetime(2026, 9, 5, 19, 15)
    assert rows[0].counterparty_name == "Ravi Auto" and rows[0].external_id == "512345678904"


def test_semicolon_and_debit_credit_columns_and_dates():
    text = ("Txn Date;Description;Debit;Credit;Balance\n"
            "01-Sep-2026;UPI/DR/612345678901/MEENA/YBL/meena.k@ybl;2,000.00;;48,000.00\n"
            "02/09/26;UPI/CR/612345678902/RAJ/okaxis/raj@okaxis;;750.00;48,750.00\n")
    rows, errors = csv_import.parse(text, MAX)
    assert errors == [], errors
    assert rows[0].direction == "sent" and rows[0].amount == 2000 and rows[0].counterparty_upi == "meena.k@ybl"
    assert rows[0].balance_before == 50000 and rows[1].balance_before == 48000
    assert rows[1].occurred_at == datetime(2026, 9, 2)


def test_html_disguised_xls(user):
    html = ("<html><body><table><tr><td>Statement</td></tr>"
            "<tr><th>Date</th><th>Particulars</th><th>Withdrawal Amount (INR )</th><th>Deposit Amount (INR )</th></tr>"
            "<tr><td>04/09/2026</td><td>UPI/shop@ybl</td><td>300</td><td></td></tr></table></body></html>")
    r = upload(user, html.encode(), "OpTransactionHistory.xls")
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1


def test_email_addresses_are_not_mistaken_for_upi_ids():
    rows, _ = csv_import.parse("Date,Amount,Type,Narration\n2026-09-01,100,debit,refund to a.b@gmail.com\n", MAX)
    assert rows[0].counterparty_upi is None


@pytest.mark.parametrize("data,name,msg", [
    (b"", "x.csv", "empty"),
    (b"Name,UPI\nA,a@ybl\n", "x.csv", "Missing required column"),
    (b"not really excel", "x.xlsx", "real Excel"),
    (b"PK\x03\x04garbage", "x.xlsx", "Couldn't open"),
])
def test_bad_files(user, data, name, msg):
    r = upload(user, data, name)
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_zip_bomb_is_refused(user, monkeypatch):
    monkeypatch.setattr(csv_import, "MAX_UNZIPPED", 10_000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", "0" * 50_000)
    r = upload(user, buf.getvalue(), "big.xlsx")
    assert r.status_code == 400 and "too large" in r.json()["detail"]


def test_upload_size_limit_and_auth(user, client):
    from app import config
    big = b"x" * (config.MAX_UPLOAD_BYTES + 1)
    assert upload(user, big, "big.csv").status_code == 413
    from fastapi.testclient import TestClient
    from app.main import app
    assert upload(TestClient(app), xlsx(BANK), "s.xlsx").status_code == 401
