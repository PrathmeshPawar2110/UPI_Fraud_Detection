"""Message, URL, QR and UPI-ID scanners (engine level and API)."""

import pytest

from app.engine import message as M, qr as Q, upi as U, urls as URL
from app.engine.redact import redact


# ---------- messages ----------

@pytest.mark.parametrize("text,code", [
    ("Your OTP is needed. Please share the OTP with our executive to stop the debit.", "CREDENTIAL_REQUEST"),
    ("Sir otp bhejo jaldi warna account band ho jayega", "CREDENTIAL_REQUEST"),
    ("Dear customer your KYC has expired, update KYC now or your account will be blocked", "KYC_THREAT"),
    ("Please install AnyDesk so our engineer can fix your UPI", "REMOTE_ACCESS"),
    ("Congratulations! You have won Rs 25,00,000 in the KBC lucky draw", "PRIZE"),
    ("Bhai galti se 5000 bhej diya, please wapas bhej do", "WRONG_TRANSFER"),
    ("Scan this QR and enter pin to receive your cashback", "RECEIVE_PIN_TRICK"),
    ("This is CBI. Your parcel contains drugs. You are under digital arrest.", "IMPERSONATION_AUTHORITY"),
    ("Your electricity will be disconnected tonight at 9:30 pm, call 9876543210", "BILL_DISCONNECT"),
    ("Part time job: earn ₹5000 daily by liking YouTube videos", "TASK_JOB"),
    ("Guaranteed returns! Double your money in our VIP trading group", "INVESTMENT"),
])
def test_message_indicators(text, code):
    r = M.analyze(text)
    assert code in {i["code"] for i in r["indicators"]}, r


def test_otp_request_alone_is_high_risk():
    assert M.analyze("Please share the OTP sent to your phone")["level"] == "high"


def test_kyc_phishing_sms_extracts_and_flags():
    r = M.analyze("SBI: your account will be blocked today. Update KYC: http://sbi-kyc-update.example/verify "
                  "or call +91 98765 43210. Pay Rs 10 to kyc.verify@ybl")
    assert r["level"] == "high"
    assert r["extracted"]["upi_ids"] == ["kyc.verify@ybl"]
    assert r["extracted"]["phones"] == ["+919876543210"]
    assert r["extracted"]["amounts"] == [10.0]
    assert "SBI" in r["extracted"]["brands"]
    assert any(u["verdict"] == "HIGH RISK" for u in r["extracted"]["urls"])


def test_ordinary_message_has_no_indicators_and_is_not_called_safe():
    r = M.analyze("Hi, dinner at 8? I'll pay you back for the movie tickets tomorrow.")
    assert r["level"] == "low" and r["indicators"] == []
    assert "No known scam indicators" in r["summary"]


def test_devanagari_keywords():
    assert M.analyze("आपका खाता बंद हो जाएगा, ओटीपी भेजें")["level"] in ("medium", "high")


# ---------- URLs ----------

@pytest.mark.parametrize("url,verdict", [
    ("https://www.onlinesbi.sbi/", "SAFE"),
    ("https://www.hdfc.bank.in/login", "SAFE"),
    ("https://cybercrime.gov.in", "SAFE"),
    ("https://bit.ly/3xYz", "UNKNOWN"),                       # one weak heuristic is not enough
    ("https://example.org/recipes", "UNKNOWN"),
    ("http://192.168.10.5/pay", "SUSPICIOUS"),
    ("https://sbi-kyc-update.example/verify", "HIGH RISK"),   # demo block list
    ("http://sbi-secure-login.xyz/kyc/update", "HIGH RISK"),  # brand mismatch + lures + risky TLD
    ("https://www.onlinesbi.sbi@evil.example/", "SUSPICIOUS"),  # userinfo trick
    ("javascript:alert(1)", "HIGH RISK"),
])
def test_url_verdicts(url, verdict):
    r = URL.analyze(url)
    assert r["verdict"] == verdict, r


def test_url_never_fetched_and_basis_explained():
    r = URL.analyze("https://bit.ly/abc")
    assert "never opened" in r["basis"]
    assert any(s["code"] == "SHORTENER" for s in r["signals"])


@pytest.mark.parametrize("bad", ["not a url", "http://", "ht!tp://###", "   "])
def test_malformed_urls_are_unknown(bad):
    assert URL.analyze(bad)["verdict"] == "UNKNOWN"


def test_punycode_and_secret_params():
    assert any(s["code"] == "PUNYCODE" for s in URL.analyze("https://xn--sbi-xyz.com")["signals"])
    assert URL.analyze("http://claim-reward.top/?otp=1234")["verdict"] in ("SUSPICIOUS", "HIGH RISK")


# ---------- QR ----------

def test_upi_qr_parsed():
    r = Q.analyze("upi://pay?pa=sharmastore@ybl&pn=Sharma%20Store&am=250&cu=INR&mc=5411")
    assert r["kind"] == "upi"
    p = r["payment"]
    assert (p["payee_vpa"], p["payee_name"], p["amount"], p["merchant_code"], p["app"]) == \
        ("sharmastore@ybl", "Sharma Store", 250.0, "5411", "PhonePe")
    assert r["level"] == "low"


def test_receive_trick_qr_is_high():
    r = Q.analyze("upi://pay?pa=cashback.reward@ybl&pn=Cashback%20Reward&am=2000&tn=Scan%20to%20receive%20cashback")
    assert r["level"] == "high"
    assert {"RECEIVE_TRICK", "NAME_LURE"} <= {w["code"] for w in r["warnings"]}


def test_invalid_payee_and_non_payment_qr():
    assert Q.analyze("upi://pay?pa=not-a-vpa&am=10")["level"] == "high"
    assert Q.analyze("upi://mandate?pa=shop@ybl&am=999")["level"] in ("medium", "high")
    assert Q.analyze("hello world")["kind"] == "text"
    assert Q.analyze("https://bit.ly/x")["kind"] == "url"


def test_new_recipient_and_reports_raise_qr_risk():
    base = Q.analyze("upi://pay?pa=someone@ybl")
    assert Q.analyze("upi://pay?pa=someone@ybl", known_party=False, reports=3)["score"] > base["score"]


# ---------- UPI IDs ----------

@pytest.mark.parametrize("vpa,valid,app", [
    ("rahul.k@okaxis", True, "Google Pay"), ("9876543210@ybl", True, "PhonePe"), ("shop@paytm", True, "Paytm"),
    ("abc@newhandle", True, None), ("no-at-sign", False, None), ("a@b", False, None),
    ("x@@ybl", False, None), ("<script>@ybl", False, None), ("' OR 1=1 --@ybl", False, None),
])
def test_vpa_validation_and_handles(vpa, valid, app):
    r = U.inspect(vpa)
    assert r["valid"] is valid and r["app"] == app


def test_lure_words_but_not_ordinary_names():
    assert any(s["code"] == "LURE_WORDS" for s in U.inspect("kycupdate.helpdesk@ybl")["signals"])
    assert any(s["code"] == "LURE_WORDS" for s in U.inspect("sbi.refund@ybl")["signals"])
    for name in ("oscar.d@okaxis", "taxila99@ybl", "prakash@oksbi"):
        assert not any(s["code"] == "LURE_WORDS" for s in U.inspect(name)["signals"]), name


# ---------- redaction ----------

@pytest.mark.parametrize("raw,leak", [
    ("Your OTP is 482913, do not share", "482913"),
    ("UPI PIN: 1234", "1234"),
    ("card 4111 1111 1111 1111 cvv 123", "4111 1111 1111 1111"),
])
def test_secrets_are_masked(raw, leak):
    assert leak not in redact(raw)


# ---------- API ----------

def test_scanner_endpoints_work_without_account(client):
    assert client.post("/api/message/analyze", json={"text": "share otp now"}).json()["level"] == "high"
    assert client.post("/api/url/analyze", json={"url": "https://bit.ly/x"}).json()["verdict"] == "UNKNOWN"
    assert client.post("/api/qr/analyze", json={"payload": "upi://pay?pa=a.b@ybl"}).json()["kind"] == "upi"
    r = client.get("/api/upi/kyc.refund@ybl").json()
    assert r["valid"] and r["level"] == "medium" and r["history"] is None


@pytest.mark.parametrize("path,body", [
    ("/api/message/analyze", {"text": ""}),
    ("/api/message/analyze", {"text": "x" * 5001}),
    ("/api/url/analyze", {"url": "x" * 2001}),
    ("/api/qr/analyze", {}),
])
def test_scanner_input_limits(client, path, body):
    assert client.post(path, json=body).status_code == 400
