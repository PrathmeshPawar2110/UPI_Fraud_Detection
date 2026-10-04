"""Statements that give only dates, and telling real repeated payments from duplicates (made-up data)."""

from app.engine import patterns as P


def upload_csv(client, text):
    return client.post("/api/transactions/import-file", params={"name": "s.csv"}, content=text.encode(),
                       headers={"Content-Type": "application/octet-stream"})


# A busy day on a date-only statement: every row lands at 00:00, which must not read as
# "5 payments within 5 minutes" or as a midnight payment.
BUSY_DAY = "Date,Narration,Debit,Credit,Balance\n" + "".join(
    f"10.04.2026,UPI/Shop {i}/shop{i}@ybl/UPI/YES BANK/60123456789{i}/,{a},,{b}\n"
    for i, (a, b) in enumerate([(2000, 48000), (2000, 46000), (2000, 44000), (2000, 42000), (75, 41925), (16, 41909)]))


def test_date_only_rows_skip_time_based_checks(user):
    r = upload_csv(user, BUSY_DAY)
    assert r.status_code == 200 and r.json()["imported"] == 6
    for t in user.get("/api/transactions").json()["items"]:
        risk = user.get(f"/api/transactions/{t['id']}").json()["risk"]
        codes = {p["code"] for p in risk["components"]["patterns"]["items"]}
        assert not codes & {"RAPID_TRANSFER", "TRANSACTION_BURST", "UNUSUAL_HOUR"}, codes
        assert t["risk_level"] == "low"


def test_time_known_only_for_real_times():
    class T:
        def __init__(self, when, source):
            from datetime import datetime
            self.occurred_at, self.source = datetime.fromisoformat(when), source
    assert not P.time_known(T("2026-04-10T00:00:00", "csv"))
    assert P.time_known(T("2026-04-10T00:05:00", "csv"))
    assert P.time_known(T("2026-04-10T00:00:00", "manual"))  # typed in by the user: trust it


def test_repeated_payments_are_not_duplicates(user):
    text = ("Date,Narration,Debit,Credit,Balance\n"
            # same day, same amount, same payee: told apart by the running balance
            "10.04.2026,NACH SIP,2000,,8000\n10.04.2026,NACH SIP,2000,,6000\n"
            # a payment, its refund (same reference), and the same amount again (new reference)
            "17.03.2026,UPI/ZOMATO/payzomato@hdfc/644221888000/,454.90,,5545.10\n"
            "17.03.2026,UPI/ZOMATO/payzomato@hdfc/644221888000/,,454.90,6000\n"
            "17.03.2026,UPI/ZOMATO/payzomato@hdfc/644248971862/,454.90,,5545.10\n"
            # interest credits that both carry the account number, which looks like a reference
            "30.03.2026,104501001157:Int.Pd:31-12-2025 to 29-03-2026,,107,5652.10\n"
            "30.06.2026,104501001157:Int.Pd:30-03-2026 to 29-06-2026,,135,5787.10\n")
    r = upload_csv(user, text).json()
    assert r["imported"] == 7 and r["duplicates"] == 0
    again = upload_csv(user, text).json()
    assert again["imported"] == 0 and again["duplicates"] == 7


def test_unreadable_file_explains_the_first_problem(user):
    r = upload_csv(user, "Date,Amount,Narration\n10.04.2026,500,Shop\n11.04.2026,600,Shop\n")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail.startswith("Couldn't read any payments") and "line 2" in detail
