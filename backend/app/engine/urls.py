"""Payment-link / URL risk heuristics. Never fetches the URL (no redirects followed, no SSRF risk).

Verdicts:
- SAFE       the domain is a known official one (or a regulator-restricted .bank.in / .gov.in domain)
             and no warning signs were found
- SUSPICIOUS combined score >= 0.35
- HIGH RISK  combined score >= 0.70
- UNKNOWN    no strong warning signs, but the site can't be verified (a single weak heuristic,
             e.g. a link shortener, is never enough for a malicious verdict)
"""

import ipaddress
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from .risk import noisy_or

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy", "shorturl.at", "tiny.cc",
              "ow.ly", "s.id", "rebrand.ly", "t.ly", "bitly.com", "v.gd", "shorte.st", "lnkd.in", "surl.li"}
RISKY_TLDS = {"xyz", "top", "click", "live", "shop", "online", "site", "icu", "buzz", "rest", "cyou", "monster",
              "loan", "work", "support", "help", "info", "tk", "ml", "ga", "cf", "gq"}
LURE_WORDS = ["login", "verify", "kyc", "update", "secure", "account", "reward", "refund", "claim", "bonus",
              "free", "gift", "cashback", "otp", "unlock", "suspend", "blocked", "aadhaar", "pan"]
# brand keyword -> official registrable domains (best effort; .bank.in / .gov.in / .nic.in also count)
BRANDS = {
    "sbi": ["sbi.co.in", "onlinesbi.sbi", "sbi.bank.in", "onlinesbi.com"],
    "hdfc": ["hdfcbank.com", "hdfc.bank.in", "hdfcbank.bank.in", "hdfc.com"],
    "icici": ["icicibank.com", "icici.bank.in", "icicibank.bank.in"],
    "axis": ["axisbank.com", "axis.bank.in", "axisbank.bank.in"],
    "kotak": ["kotak.com", "kotak.bank.in", "kotakbank.bank.in"],
    "paytm": ["paytm.com", "paytmbank.com"],
    "phonepe": ["phonepe.com"],
    "gpay": ["google.com", "pay.google.com"], "googlepay": ["google.com"],
    "npci": ["npci.org.in"], "bhim": ["bhimupi.org.in", "npci.org.in"],
    "rbi": ["rbi.org.in"], "incometax": ["incometax.gov.in"], "uidai": ["uidai.gov.in"],
    "aadhaar": ["uidai.gov.in", "myaadhaar.uidai.gov.in"], "epfo": ["epfindia.gov.in"],
    "irctc": ["irctc.co.in"], "amazon": ["amazon.in", "amazon.com"], "flipkart": ["flipkart.com"],
}
OFFICIAL = {d for ds in BRANDS.values() for d in ds} | {"cybercrime.gov.in", "sancharsaathi.gov.in"}
RESTRICTED_SUFFIXES = (".bank.in", ".gov.in", ".nic.in")  # registration restricted (RBI / government)
# Clearly fictional entries for the demo (".example" is reserved and never resolves).
DEMO_UNSAFE = {"sbi-kyc-update.example", "refund-npci.example", "paytm-cashback.example"}

SECOND_LEVEL = {"co.in", "org.in", "net.in", "gov.in", "nic.in", "bank.in", "fin.in", "ac.in", "co.uk", "com.au"}


def registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def analyze(raw: str, reports: int = 0) -> dict:
    text = (raw or "").strip()
    signals = []

    def add(code, weight, msg, kind="warning"):
        signals.append({"code": code, "weight": weight, "text": msg, "kind": kind})

    if not text:
        return _result(text, None, [], "UNKNOWN", 0.0, "Enter a link to check.")
    lower = text.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        add("SCRIPT_SCHEME", 0.8, "This is a script/data link, not a web page. Never open it.")
        return _finish(text, None, signals)
    if lower.startswith("upi:"):
        return _result(text, None, [{"code": "UPI_LINK", "weight": 0, "kind": "info",
                                     "text": "This is a UPI payment link. Check it in the QR / UPI link scanner."}],
                       "UNKNOWN", 0.0, "UPI payment link")

    candidate = text if re.match(r"^[a-z][a-z0-9+.-]*://", lower) else "http://" + text
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        host = ""
    if not host or " " in host or (not re.fullmatch(r"[a-z0-9.-]+", host) and not host.startswith("[")):
        return _result(text, None, [], "UNKNOWN", 0.0, "This doesn't look like a valid web address.")
    if parts.scheme not in ("http", "https"):
        add("ODD_SCHEME", 0.3, f"Uses the unusual '{parts.scheme}:' scheme.")

    path = unquote(parts.path + "?" + parts.query).lower()
    is_ip = _is_ip(host)
    domain = host if is_ip else registrable(host)

    if parts.username or "@" in parts.netloc:
        add("USERINFO", 0.5, "The address contains '@'. Everything before '@' is ignored by the browser, "
                             "a classic trick to show a trusted name while opening another site.")
    if is_ip:
        add("IP_HOST", 0.45, "The link points to a raw IP address instead of a named website.")
    if "xn--" in host:
        add("PUNYCODE", 0.4, "The domain uses look-alike (punycode) characters that can imitate a real brand.")
    if domain in SHORTENERS:
        add("SHORTENER", 0.25, "A link shortener hides the real destination. We don't open links, so the target is unknown.")
    if domain in DEMO_UNSAFE:
        add("DEMO_BLOCKLIST", 0.8, "On UPI Guard's demo block list (synthetic example).")
    if parts.scheme == "http":
        add("NO_HTTPS", 0.1, "Not encrypted (http). HTTPS alone doesn't make a site safe, but payment pages always use it.")

    tld = host.rsplit(".", 1)[-1]
    if not is_ip and tld in RISKY_TLDS:
        add("RISKY_TLD", 0.25, f"'.{tld}' domains are cheap and common in phishing campaigns.")
    if not is_ip and (host.count(".") >= 4 or len(host) > 45):
        add("COMPLEX_HOST", 0.15, "Unusually long or deeply nested domain name.")

    official = domain in OFFICIAL or host in OFFICIAL or host.endswith(RESTRICTED_SUFFIXES)
    brands = [b for b in BRANDS if b in host.replace("-", "") or b in path.replace("-", "")]
    if brands and not official:
        add("BRAND_MISMATCH", 0.55, f"Mentions '{brands[0]}' but the domain ({domain}) isn't an official "
                                    f"{brands[0].upper()} domain.")
    lures = [w for w in LURE_WORDS if w in host or w in path]
    if lures and not official:
        add("LURE_WORDS", min(0.15 * len(lures), 0.3), f"Contains '{', '.join(lures[:3])}', typical of phishing pages.")
    if any(k in ("pin", "mpin", "otp", "cvv") for k, _ in parse_qsl(parts.query)):
        add("SECRET_PARAM", 0.5, "The link carries an OTP/PIN field. No genuine service puts these in a link.")
    if reports:
        add("REPORTED", min(0.2 + 0.1 * (reports - 1), 0.45),
            f"Reported by {reports} UPI Guard user{'s' if reports > 1 else ''} (unverified).")
    if official:
        add("OFFICIAL", 0, "Known official or regulator-restricted domain"
            + (" (.bank.in is only issued to RBI-regulated banks)." if host.endswith(".bank.in") else "."), "good")

    return _finish(text, {"host": host, "domain": domain, "scheme": parts.scheme, "official": official}, signals)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return bool(re.fullmatch(r"\d+", host))  # decimal-encoded IPs like http://3232235777


def _finish(text, info, signals) -> dict:
    s = noisy_or(x["weight"] for x in signals)
    official = bool(info and info["official"])
    if s >= 0.70:
        verdict, summary = "HIGH RISK", "Several strong warning signs. Don't open it or enter any details."
    elif s >= 0.35:
        verdict, summary = "SUSPICIOUS", "Warning signs found. Don't pay or log in through this link."
    elif official and s < 0.15:
        verdict, summary = "SAFE", "Known official domain and no warning signs. Still, never share OTP or PIN."
    else:
        verdict, summary = "UNKNOWN", "No strong warning signs, but we can't verify this site. Prefer the official app."
    return _result(text, info, signals, verdict, s, summary)


def _result(text, info, signals, verdict, score, summary) -> dict:
    return {"input": text[:500], "verdict": verdict, "score": round(score, 3), "summary": summary,
            "url": info, "signals": signals,
            "basis": "Heuristics on the address only; the link is never opened."}
