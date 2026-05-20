from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from enum import StrEnum

from django.conf import settings


class OtpPurpose(StrEnum):
    ACTIVATE = "activate"
    PASSWORD_RESET = "password_reset"


def _redis_client():
    import redis

    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _otp_key(purpose: OtpPurpose, email: str) -> str:
    return f"users:otp:{purpose.value}:{email.lower().strip()}"


def _reset_session_key(token: str) -> str:
    return f"users:pwd_reset:{token}"


def _digest(otp: str) -> str:
    return hmac.new(
        settings.OTP_PEPPER.encode(),
        otp.encode(),
        hashlib.sha256,
    ).hexdigest()


def generate_numeric_otp(length: int | None = None) -> str:
    length = length or settings.OTP_LENGTH
    return "".join(secrets.choice("0123456789") for _ in range(length))


def store_otp(purpose: OtpPurpose, email: str, otp: str) -> None:
    payload = {"digest": _digest(otp), "attempts": 0}
    r = _redis_client()
    key = _otp_key(purpose, email)
    r.setex(key, settings.OTP_TTL_SECONDS, json.dumps(payload))


def verify_otp(purpose: OtpPurpose, email: str, otp: str) -> bool:
    r = _redis_client()
    key = _otp_key(purpose, email)
    raw = r.get(key)
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        r.delete(key)
        return False

    attempts = int(data.get("attempts", 0))
    if attempts >= settings.OTP_MAX_ATTEMPTS:
        r.delete(key)
        return False

    digest = data.get("digest")
    if not digest or not secrets.compare_digest(digest, _digest(otp)):
        data["attempts"] = attempts + 1
        ttl = r.ttl(key)
        if ttl < 0:
            ttl = settings.OTP_TTL_SECONDS
        r.setex(key, ttl, json.dumps(data))
        return False

    r.delete(key)
    return True


def delete_otp(purpose: OtpPurpose, email: str) -> None:
    _redis_client().delete(_otp_key(purpose, email))


def create_password_reset_session(email: str) -> str:
    token = secrets.token_urlsafe(32)   
    r = _redis_client()
    r.setex(_reset_session_key(token), settings.OTP_TTL_SECONDS, email.lower().strip())
    return token


def consume_password_reset_session(token: str) -> str | None:
    r = _redis_client()
    key = _reset_session_key(token)
    pipe = r.pipeline()
    pipe.get(key)
    pipe.delete(key)
    email, _ = pipe.execute()
    return email
