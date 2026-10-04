"""ICICI-style PDF statement: the header is printed over three lines with "S No." centred on the middle
one, rows are separated by rules, and the payee's name sits above the line with the date.
All data here is made up."""

from datetime import datetime

from app.engine import csv_import
from tests.test_pdf_statement import pdf

X = {"sno": 30, "date": 62, "remarks": 192, "wd": 425, "dep": 480, "bal": 535}


def icici_pdf(pages=1) -> bytes:
    header = [(X["date"], 100, "Transaction", 8), (X["wd"], 100, "Withdrawal", 8), (X["dep"], 100, "Deposit", 8),
              (X["bal"], 100, "Balance", 8),
              (X["sno"], 105, "S No.", 8), (115, 105, "Cheque Number", 8), (X["remarks"] + 40, 105, "Transaction Remarks", 8),
              (X["date"] + 10, 110, "Date", 8), (X["wd"], 110, "Amount (INR)", 8), (X["dep"], 110, "Amount (INR)", 8),
              (X["bal"], 110, "(INR)", 8)]
    rows = [("1", "11.03.2026", "Tea Stall", ["UPI/Tea Stall/teastall@ybl/UPI/YES", "BANK/601234567890/ICIabc/"], "40.00", "", "9960.00"),
            ("2", "12.03.2026", "Credit trxn", ["NEFT-EMPLOYER-ABC12345"], "", "50000.00", "59960.00"),
            ("3", "13.03.2026", "QUICK PAY", ["UPI/QUICK PAY/quickpay.mule01@axl/UPI/AXIS", "BANK/601234567891/ICIdef/"], "59960.00", "", "0.00")]
    out, all_rules = [], {}
    for p in range(pages):
        cells, rules, y = [*header], [118], 125
        if p == 0:
            cells.append((40, 40, "Statement of Transactions in Saving Account XXXX for the period March 11, 2026 - March 13, 2026", 9))
        for sno, date, name, narr, wd, dep, bal in rows[p::pages] if pages > 1 else rows:
            cells += [(X["remarks"], y, name, 8),                     # the name, above the date
                      (X["sno"], y + 5, sno, 8), (X["date"], y + 5, date, 8)]
            cells += [(x, y + 3, v, 8) for x, v in ((X["wd"], wd), (X["dep"], dep), (X["bal"], bal)) if v]
            cells += [(X["remarks"], y + 10 + 10 * i, t, 8) for i, t in enumerate(narr)]
            y += 12 + 10 * len(narr)
            rules.append(y - 3)
            y += 4
        cells.append((40, 800, "Never share your OTP, CVV or passwords with anyone.", 8))
        out.append(cells)
        all_rules[p] = rules
    return pdf(out, rules=all_rules)


def test_three_line_header_rules_and_name_above_date():
    rows, errors = csv_import.parse_file("OpTransactionHistory.pdf", icici_pdf(), 2000)
    assert errors == []
    assert [(r.direction, r.amount) for r in rows] == [("sent", 40), ("received", 50000), ("sent", 59960)]
    tea, salary, drain = rows
    assert tea.occurred_at == datetime(2026, 3, 11) and tea.counterparty_name == "Tea Stall"
    assert tea.counterparty_upi == "teastall@ybl" and tea.external_id == "601234567890"
    assert tea.balance_before == 10000 and drain.balance_before == 59960
    assert salary.counterparty_name == "Credit trxn" and drain.counterparty_name == "QUICK PAY"


def test_header_repeated_on_every_page():
    rows, errors = csv_import.parse_file("s.pdf", icici_pdf(pages=3), 2000)
    assert errors == [] and len(rows) == 3
    assert sorted(r.counterparty_name for r in rows) == ["Credit trxn", "QUICK PAY", "Tea Stall"]


def test_upload_flags_the_drain(user):
    r = user.post("/api/transactions/import-file", params={"name": "s.pdf"}, content=icici_pdf(),
                  headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 3 and r.json()["flagged"][0]["counterparty_upi"] == "quickpay.mule01@axl"
