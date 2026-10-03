"""Accounts and sessions using only the standard library.

- Passwords: scrypt (hashlib), random 16-byte salt, constant-time comparison.
- Sessions: HMAC-SHA256-signed token in an HttpOnly, SameSite=Strict cookie (Secure over HTTPS).
  The token embeds a fingerprint of the password hash, so changing the password or deleting the
  account invalidates existing sessions.
- Login throttling: 5 failed attempts per email per 15 minutes.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import AuditLog, LoginAttempt, User, utcnow

COOKIE = "upig_session"
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
MAX_FAILED, FAILED_WINDOW = 5, timedelta(minutes=15)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        check = hashlib.scrypt(password.encode(), salt=_unb64(salt), dklen=32, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(check, _unb64(digest))
    except (ValueError, TypeError):
        return False


# ---------- session tokens ----------

def _fingerprint(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def make_token(user: User) -> str:
    payload = {"uid": user.id, "fp": _fingerprint(user), "exp": int(time.time()) + config.SESSION_DAYS * 86400}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return body + "." + _b64(_sign(body))


def read_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(_unb64(sig), _sign(body)):
            return None
        payload = json.loads(_unb64(body))
        return payload if payload["exp"] > time.time() else None
    except (ValueError, KeyError, TypeError):
        return None


def _sign(body: str) -> bytes:
    return hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------- dependencies ----------

def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    payload = read_token(request.cookies.get(COOKIE, ""))
    if not payload:
        return None
    user = db.get(User, payload["uid"])
    return user if user and hmac.compare_digest(payload["fp"], _fingerprint(user)) else None


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


def audit(db: Session, user_id: int | None, action: str, **detail) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def set_session(response: Response, request: Request, user: User) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, make_token(user), max_age=config.SESSION_DAYS * 86400,
                        httponly=True, samesite="strict", secure=secure, path="/")


# ---------- API ----------

class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Please enter a valid email address.")
        return v


class Signup(Credentials):
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(default="", max_length=80)


class Me(BaseModel):
    id: int
    email: str
    display_name: str
    settings: dict


def me_out(user: User) -> Me:
    return Me(id=user.id, email=user.email, display_name=user.display_name, settings=user.settings or {})


@router.post("/signup", response_model=Me)
def signup(body: Signup, request: Request, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(email=body.email, password_hash=hash_password(body.password),
                display_name=body.display_name.strip(),
                settings={"ai_consent": False, "notifications": False, "demo_mode": False})
    db.add(user)
    db.flush()
    audit(db, user.id, "auth.signup")
    db.commit()
    set_session(response, request, user)
    return me_out(user)


@router.post("/login", response_model=Me)
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    since = utcnow() - FAILED_WINDOW
    failed = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.email == body.email, LoginAttempt.success.is_(False), LoginAttempt.created_at >= since))
    if failed >= MAX_FAILED:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.email == body.email))
    ok = user is not None and verify_password(body.password, user.password_hash)
    db.add(LoginAttempt(email=body.email, success=ok))
    if not ok:
        db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    audit(db, user.id, "auth.login")
    db.commit()
    set_session(response, request, user)
    return me_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=Me)
def me(user: User = Depends(current_user)):
    return me_out(user)
