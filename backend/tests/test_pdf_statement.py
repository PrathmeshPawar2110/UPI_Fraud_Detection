"""PDF statement upload: table rebuilt from text positions, wrapped cells, repeated headers, locked PDFs."""

import io
from datetime import datetime
from urllib.parse import quote

from app.engine import csv_import

MAX = 2000


def pdf(pages, height=842, rules=None) -> bytes:
    """A minimal PDF: each page is a list of (x, y-from-top, text, size) drawn in Helvetica, plus optional
    horizontal rules ({page: [y-from-top, …]}) drawn across the table, like a bank's row separators."""
    esc = lambda t: t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for n, cells in enumerate(pages):
        drawn = "".join(f"0.5 w 20 {height - y} m 575 {height - y} l S\n" for y in (rules or {}).get(n, []))
        stream = (drawn + "".join(f"BT /F1 {size} Tf {x} {height - y} Td ({esc(t)}) Tj ET\n"
                                  for x, y, t, size in cells)).encode("latin-1")
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 {height}] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {len(objs)} 0 R >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + (o if isinstance(o, bytes) else o.encode("latin-1")) + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    out.write("".join(f"{o:010d} 00000 n \n" for o in offsets).encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


COLS = [40, 110, 300, 380, 440, 510]  # Date, Narration, Ref, Withdrawal, Deposit, Balance


def bank_row(y, date, narr, ref, wd, dep, bal, more=None):
    cells = [(COLS[0], y, date, 8), (COLS[1], y, narr, 8), (COLS[2], y, ref, 8)]
    cells += [(x, y, v, 8) for x, v in zip(COLS[3:], (wd, dep, bal)) if v]
    if more:
        cells.append((COLS[1], y + 10, more, 8))  # narration wraps onto a second line
    return cells


def bank_pdf() -> bytes:
    header = [(COLS[0], 120, "Date", 8), (COLS[1], 120, "Narration", 8), (COLS[2], 120, "Chq./Ref.No.", 8),
              (COLS[3], 120, "Withdrawal", 8), (COLS[3], 130, "Amt.", 8),     # two-line header
              (COLS[4], 120, "Deposit", 8), (COLS[4], 130, "Amt.", 8),
              (COLS[5], 120, "Closing", 8), (COLS[5], 130, "Balance", 8)]
    page1 = [(40, 40, "XYZ BANK LTD - Statement of account", 12), (40, 60, "Account No: XXXX1234   Period: 01/09/2026 to 05/09/2026", 9),
             *header,
             *bank_row(150, "01/09/26", "UPI-CHAI POINT-", "412345678901", "240.00", "", "41,760.00", "chaipoint.ka@ybl-YESB0000001"),
             *bank_row(180, "01/09/26", "UPI-FRESH MART-", "412345678902", "1,200.00", "", "40,560.00", "freshmart.blr@okaxis"),
             *bank_row(210, "02/09/26", "NEFT-EMPLOYER PAYROLL", "N1234", "", "62,000.00", "1,02,560.00"),
             (40, 800, "Page 1 of 2   This is a computer generated statement.", 7)]
    page2 = [*[(x, y - 60, t, s) for x, y, t, s in header],
             *bank_row(100, "03/09/26", "UPI-QUICK PAY-", "412345678903", "1,02,560.00", "", "0.00", "quickpay.mule01@axl"),
             (40, 200, "STATEMENT SUMMARY  Opening Balance 42,000.00  Debits 3  Credits 1", 8),
             (40, 800, "Page 2 of 2", 7)]
    return pdf([page1, page2])


def wallet_pdf() -> bytes:
    cells = [(40, 50, "Transaction Statement for 98XXXXXX10", 12),
             (40, 100, "Date", 9), (150, 100, "Transaction Details", 9), (420, 100, "Type", 9), (500, 100, "Amount", 9)]
    y = 130
    for date, tm, detail, txid, utr, kind, amt in [
        ("Oct 01, 2026", "12:25 am", "Paid to JIO Postpaid", "T2610010025123", "512345678911", "DEBIT", "Rs.2,824.92"),
        ("Sep 13, 2026", "11:09 pm", "Received from Girish Kumbhar", "T2609132309456", "512345678912", "CREDIT", "Rs.300"),
    ]:
        cells += [(40, y, date, 9), (150, y, detail, 9), (420, y, kind, 9), (500, y, amt, 9),
                  (40, y + 12, tm, 8), (150, y + 12, f"Transaction ID {txid}", 8), (150, y + 24, f"UTR No. {utr}", 8),
                  (150, y + 36, "Paid by XXXXXX1234", 8)]
        y += 70
    return pdf([cells])


def upload(client, data, name, password=None):
    headers = {"Content-Type": "application/octet-stream"}
    if password is not None:
        headers["X-File-Password"] = quote(password)
    return client.post("/api/transactions/import-file", params={"name": name}, content=data, headers=headers)


def test_bank_pdf_rows():
    rows, errors = csv_import.parse_file("statement.pdf", bank_pdf(), MAX)
    assert errors == []
    assert [(r.direction, r.amount) for r in rows] == [("sent", 240), ("sent", 1200), ("received", 62000), ("sent", 102560)]
    assert rows[0].counterparty_upi == "chaipoint.ka@ybl" and rows[0].external_id == "412345678901"
    assert rows[0].balance_before == 42000 and rows[3].balance_before == 102560
    assert rows[3].occurred_at == datetime(2026, 9, 3)


def test_wallet_pdf_with_wrapped_cells():
    rows, errors = csv_import.parse_file("PhonePe_Statement.pdf", wallet_pdf(), MAX)
    assert errors == []
    jio, girish = rows
    assert (jio.direction, jio.amount, jio.counterparty_name) == ("sent", 2824.92, "JIO Postpaid")
    assert jio.occurred_at == datetime(2026, 10, 1, 0, 25) and jio.external_id == "512345678911"
    assert (girish.direction, girish.amount, girish.counterparty_name) == ("received", 300, "Girish Kumbhar")
    assert girish.occurred_at == datetime(2026, 9, 13, 23, 9)


def test_pdf_upload_flags_the_drain(user):
    r = upload(user, bank_pdf(), "statement.pdf")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 4 and body["flagged"][0]["counterparty_upi"] == "quickpay.mule01@axl"
    assert upload(user, bank_pdf(), "statement.pdf").json()["duplicates"] == 4


def test_locked_pdf_needs_the_password(user):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(wallet_pdf())))
    w.encrypt("DOB0101", algorithm="AES-256")
    buf = io.BytesIO()
    w.write(buf)
    locked = buf.getvalue()
    r = upload(user, locked, "e-statement.pdf")
    assert r.status_code == 423 and "password" in r.json()["detail"]
    r = upload(user, locked, "e-statement.pdf", password="wrong")
    assert r.status_code == 423 and r.json()["detail"] == "Wrong password."
    r = upload(user, locked, "e-statement.pdf", password="DOB0101")
    assert r.status_code == 200 and r.json()["imported"] == 2


def test_pdf_without_text_or_table(user):
    r = upload(user, pdf([[]]), "scan.pdf")
    assert r.status_code == 400 and "no readable text" in r.json()["detail"]
    r = upload(user, pdf([[(40, 100, "Dear customer, thank you for banking with us.", 10)]]), "letter.pdf")
    assert r.status_code == 400 and "table of payments" in r.json()["detail"]
    r = upload(user, b"%PDF-1.4 garbage", "broken.pdf")
    assert r.status_code == 400
    r = upload(user, b"hello", "fake.pdf")
    assert r.status_code == 400 and "real PDF" in r.json()["detail"]
