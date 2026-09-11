"""Primitives d'authentification sans état secret conservé côté client."""

from __future__ import annotations

import hashlib
import os
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Response
from sqlalchemy.orm import Session

from acp_database.models import UserModel, UserSessionModel

SESSION_COOKIE_NAME = "acp_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
_OWNER_MARKER = "platform-owner"
_PASSWORD_HASHER = PasswordHasher()
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class AuthContext:
    user: UserModel
    session: UserSessionModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_login(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate_hash = password_hash or _DUMMY_PASSWORD_HASH
    try:
        valid = _PASSWORD_HASHER.verify(candidate_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False
    return bool(password_hash) and valid


def password_needs_rehash(password_hash: str) -> bool:
    return _PASSWORD_HASHER.check_needs_rehash(password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_ttl_seconds() -> int:
    raw_value = os.environ.get("ACP_SESSION_TTL_SECONDS", "43200")
    try:
        value = int(raw_value)
    except ValueError:
        value = 43200
    return max(300, min(value, 2_592_000))


def session_cookie_secure() -> bool:
    return os.environ.get("ACP_SESSION_COOKIE_SECURE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def create_user_session(
    db: Session, user_id: str
) -> tuple[UserSessionModel, str, str]:
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = utcnow()
    session = UserSessionModel(
        user_id=user_id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        last_seen_at=now,
        expires_at=now + timedelta(seconds=session_ttl_seconds()),
    )
    db.add(session)
    return session, session_token, csrf_token


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def authenticate_session(db: Session, session_token: str | None) -> AuthContext | None:
    if not session_token:
        return None
    session = (
        db.query(UserSessionModel)
        .filter_by(token_hash=hash_token(session_token))
        .first()
    )
    if (
        session is None
        or session.revoked_at is not None
        or _as_utc(session.expires_at) <= utcnow()
    ):
        return None
    user = db.get(UserModel, session.user_id)
    if user is None or not user.is_active:
        return None
    return AuthContext(user=user, session=session)


def rotate_csrf_token(session: UserSessionModel) -> str:
    csrf_token = secrets.token_urlsafe(32)
    session.csrf_token_hash = hash_token(csrf_token)
    return csrf_token


def csrf_token_is_valid(session: UserSessionModel, csrf_token: str | None) -> bool:
    if not csrf_token:
        return False
    return secrets.compare_digest(session.csrf_token_hash, hash_token(csrf_token))


def set_session_cookie(
    response: Response, session_token: str, expires_at: datetime
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=session_ttl_seconds(),
        expires=expires_at,
        path="/",
        secure=session_cookie_secure(),
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=session_cookie_secure(),
        httponly=True,
        samesite="strict",
    )


def owner_marker() -> str:
    return _OWNER_MARKER
