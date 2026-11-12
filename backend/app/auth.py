"""Authentication (JWT, OAuth2 password flow) and role / branch authorization.

Enforcement lives here, on the API, never only in the UI:

* ``current_user`` loads the user named by the token's ``sub`` from the database on every
  request and uses the *live* role, branch and is_active. The role and branch_id claims in
  the token are only hints, so a deactivated user or a changed branch takes effect at once.
* ``active_user`` additionally blocks users who still have to change their password.
* ``admin_user`` is for admin-only endpoints.
* ``branch_scope`` resolves the branch a request may see: an admin may ask for any branch
  (or all), a branch manager only ever sees their own, and asking for another one is 403.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.storage.models import ROLE_ADMIN, AuditLog, Branch, Fridge, User
from app.storage.session import get_db

ALGORITHM = "HS256"
# Tolerance for clock differences when checking a token's iat / exp. PyJWT rejects a token
# "issued in the future" with zero tolerance by default, and VM clocks (WSL2, Docker Desktop
# after a laptop sleeps) can jump back by seconds: valid sessions then got a random 401.
CLOCK_SKEW_LEEWAY = timedelta(seconds=60)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------- passwords ----------


def hash_password(password: str) -> str:
    # BCRYPT_ROUNDS is only lowered by the test suite (speed); production keeps 12.
    rounds = int(os.environ.get("BCRYPT_ROUNDS", "12"))
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# A real hash to compare against when the username does not exist, so a login for an
# unknown user takes as long as one with a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password")


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


# ---------- tokens ----------


@lru_cache
def _persisted_secret(state_dir: str) -> str:
    """The install's own random JWT secret, created on first use and kept in STATE_DIR (a
    Docker volume), so tokens survive restarts and no secret ever lives in the repository."""
    path = Path(state_dir) / "jwt_secret"
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secret)
    tmp.chmod(0o600)
    tmp.replace(path)
    return secret


def _signing_key(settings: Settings) -> bytes:
    """HMAC-SHA256 key: SHA-256 of JWT_SECRET (or of the generated install secret), so the
    key is always 32 bytes whatever the secret's length."""
    secret = settings.jwt_secret or _persisted_secret(settings.state_dir)
    return hashlib.sha256(secret.encode("utf-8")).digest()


def create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "branch_id": user.branch_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(claims, _signing_key(settings), algorithm=ALGORITHM)


def _unauthorized(detail: str = "Not signed in.") -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


# ---------- dependencies ----------


def current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """The signed-in user, loaded from the database (live role, branch, is_active)."""
    if not token:
        raise _unauthorized()
    try:
        claims = jwt.decode(
            token, _signing_key(settings), algorithms=[ALGORITHM], leeway=CLOCK_SKEW_LEEWAY
        )
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise _unauthorized("Your session has expired. Please sign in again.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("This account is not active.")
    return user


def active_user(user: User = Depends(current_user)) -> User:
    """A signed-in user who is allowed to use the app (password change not pending)."""
    if user.must_change_password:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "code": "must_change_password",
                "message": "Please choose a new password before continuing.",
            },
        )
    return user


def admin_user(user: User = Depends(active_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise forbidden("Only an admin can do this.")
    return user


@dataclass(frozen=True)
class BranchScope:
    """Which branch a request is limited to. ``branch_id is None`` means all branches."""

    user: User
    branch_id: int | None
    branch_name: str | None

    @property
    def is_admin(self) -> bool:
        return self.user.role == ROLE_ADMIN

    def allows_branch(self, branch_id: int | None) -> bool:
        return self.branch_id is None or branch_id == self.branch_id

    def check_fridge(self, fridge: Fridge) -> None:
        if not self.allows_branch(fridge.branch_id):
            raise forbidden("This fridge belongs to another branch.")


def resolve_scope(db: Session, user: User, branch: str | None) -> BranchScope:
    if user.role == ROLE_ADMIN:
        if not branch:
            return BranchScope(user, None, None)
        b = db.scalar(select(Branch).where(Branch.name == branch))
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown branch {branch!r}.")
        return BranchScope(user, b.id, b.name)
    # Branch manager: always their own branch; asking for another one is an error, not an
    # empty result, so a crafted request cannot probe other branches.
    if user.branch_id is None:
        raise forbidden("Your account is not linked to a branch. Ask Summer to fix it.")
    own = db.get(Branch, user.branch_id)
    assert own is not None
    if branch and branch != own.name:
        raise forbidden("You can only see your own branch.")
    return BranchScope(user, own.id, own.name)


def branch_scope(
    branch: str | None = Query(None, description="Branch name (admins only; managers: own)"),
    user: User = Depends(active_user),
    db: Session = Depends(get_db),
) -> BranchScope:
    return resolve_scope(db, user, branch)


# ---------- audit ----------


def audit(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    **details: Any,
) -> None:
    """Record who did what. Never pass passwords in ``details``."""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={k: v for k, v in details.items() if v is not None} or None,
            created_at=utcnow(),
        )
    )
