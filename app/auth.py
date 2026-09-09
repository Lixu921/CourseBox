import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PASSWORD_ITERATIONS = 310_000
SESSION_TTL = timedelta(days=7)
SESSION_COOKIE = "coursebox_session"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError, base64.binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)


def new_session_token() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + SESSION_TTL).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return token, token_hash, expires_at


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()
