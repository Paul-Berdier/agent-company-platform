"""Bootstrap unique et cycle de vie des sessions utilisateur."""

import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    AuthenticatedUser,
    AuthSessionResponse,
    AuthStatusResponse,
    LoginRequest,
    LogoutResponse,
    OwnerBootstrapRequest,
)
from acp_database.models import UserModel

from ..deps import get_auth_context, get_db, require_csrf
from ..security import (
    AuthContext,
    clear_session_cookie,
    create_user_session,
    hash_password,
    normalize_login,
    owner_marker,
    password_needs_rehash,
    rotate_csrf_token,
    set_session_cookie,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _public_user(user: UserModel) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        login=user.login_normalized,
        display_name=user.display_name,
        role=user.platform_role,
    )


def _session_response(
    user: UserModel, csrf_token: str, expires_at: datetime
) -> AuthSessionResponse:
    return AuthSessionResponse(
        user=_public_user(user), csrf_token=csrf_token, expires_at=expires_at
    )


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(db: Session = Depends(get_db)) -> AuthStatusResponse:
    owner_exists = (
        db.query(UserModel.id).filter_by(bootstrap_marker=owner_marker()).first()
        is not None
    )
    return AuthStatusResponse(bootstrap_required=not owner_exists)


@router.post(
    "/bootstrap",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_owner(
    body: OwnerBootstrapRequest,
    response: Response,
    bootstrap_token: str | None = Header(default=None, alias="X-ACP-Bootstrap-Token"),
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    expected_token = os.environ.get("ACP_BOOTSTRAP_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=503, detail="Initialisation indisponible")
    if not bootstrap_token or not secrets.compare_digest(
        bootstrap_token, expected_token
    ):
        raise HTTPException(status_code=403, detail="Initialisation refusée")
    if db.query(UserModel.id).filter_by(bootstrap_marker=owner_marker()).first():
        raise HTTPException(status_code=409, detail="Initialisation indisponible")

    user = UserModel(
        login_normalized=normalize_login(body.login),
        display_name=body.display_name,
        password_hash=hash_password(body.password.get_secret_value()),
        platform_role="owner",
        bootstrap_marker=owner_marker(),
        password_changed_at=utcnow(),
    )
    db.add(user)
    try:
        db.flush()
        user_session, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Initialisation indisponible"
        ) from exc
    set_session_cookie(response, session_token, user_session.expires_at)
    return _session_response(user, csrf_token, user_session.expires_at)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    body: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> AuthSessionResponse:
    user = (
        db.query(UserModel)
        .filter_by(login_normalized=normalize_login(body.login))
        .first()
    )
    password = body.password.get_secret_value()
    valid_password = verify_password(password, user.password_hash if user else None)
    if user is None or not user.is_active or not valid_password:
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        user.password_changed_at = utcnow()
    user.last_login_at = utcnow()
    user_session, session_token, csrf_token = create_user_session(db, user.id)
    db.commit()
    set_session_cookie(response, session_token, user_session.expires_at)
    return _session_response(user, csrf_token, user_session.expires_at)


@router.get("/session", response_model=AuthSessionResponse)
def read_session(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
) -> AuthSessionResponse:
    csrf_token = rotate_csrf_token(context.session)
    context.session.last_seen_at = utcnow()
    db.commit()
    return _session_response(context.user, csrf_token, context.session.expires_at)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> LogoutResponse:
    context.session.revoked_at = utcnow()
    db.commit()
    clear_session_cookie(response)
    return LogoutResponse()
