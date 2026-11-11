"""User management (admin only): create branch managers, assign a branch, reset a password,
deactivate. A reset returns the temporary password once; it is never e-mailed or logged."""

from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import admin_user, audit, hash_password, utcnow
from app.storage.models import ROLE_MANAGER, Branch, User
from app.storage.session import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    branch_id: int | None
    branch: str | None
    is_active: bool
    must_change_password: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    branch_id: int
    password: str = Field(min_length=8, max_length=72)


class UserPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    branch_id: int | None = None
    is_active: bool | None = None


class PasswordResetOut(BaseModel):
    user: UserOut
    temporary_password: str  # shown once to Summer; the user must change it at next sign-in


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        full_name=u.full_name,
        role=u.role,
        branch_id=u.branch_id,
        branch=u.branch.name if u.branch else None,
        is_active=u.is_active,
        must_change_password=u.must_change_password,
        created_at=u.created_at,
    )


def _branch(db: Session, branch_id: int) -> Branch:
    b = db.get(Branch, branch_id)
    if b is None:
        raise HTTPException(422, "Unknown branch.")
    return b


def _user(db: Session, user_id: int) -> User:
    u = db.scalar(select(User).where(User.id == user_id).options(selectinload(User.branch)))
    if u is None:
        raise HTTPException(404, "User not found.")
    return u


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[UserOut]:
    q = select(User).options(selectinload(User.branch)).order_by(User.role, User.username)
    return [user_out(u) for u in db.scalars(q)]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> UserOut:
    """Create a branch manager. They must change the initial password at first sign-in."""
    username = body.username.strip().lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, f"The username {username!r} is already taken.")
    b = _branch(db, body.branch_id)
    u = User(
        username=username,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
        role=ROLE_MANAGER,
        branch_id=b.id,
        is_active=True,
        must_change_password=True,
        created_at=utcnow(),
    )
    db.add(u)
    db.flush()
    audit(db, admin, "user.created", "user", u.id, username=username, branch=b.name)
    db.commit()
    return user_out(_user(db, u.id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserPatch,
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> UserOut:
    u = _user(db, user_id)
    if u.id == admin.id and body.is_active is False:
        raise HTTPException(409, "You cannot deactivate your own account.")
    if body.full_name is not None:
        u.full_name = body.full_name.strip()
    if body.branch_id is not None and body.branch_id != u.branch_id:
        if u.role != ROLE_MANAGER:
            raise HTTPException(409, "Only branch managers belong to a branch.")
        old = u.branch.name if u.branch else None
        b = _branch(db, body.branch_id)
        u.branch_id = b.id
        audit(
            db, admin, "user.branch_changed", "user", u.id,
            username=u.username, old_branch=old, new_branch=b.name,
        )  # fmt: skip
    if body.is_active is not None and body.is_active != u.is_active:
        u.is_active = body.is_active
        action = "user.reactivated" if body.is_active else "user.deactivated"
        audit(db, admin, action, "user", u.id, username=u.username)
    db.commit()
    return user_out(_user(db, u.id))


@router.post("/{user_id}/reset-password", response_model=PasswordResetOut)
def reset_password(
    user_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> PasswordResetOut:
    """Set a random temporary password, returned once. Not e-mailed, not logged."""
    u = _user(db, user_id)
    temp = secrets.token_urlsafe(9)
    u.password_hash = hash_password(temp)
    u.must_change_password = True
    audit(db, admin, "user.password_reset", "user", u.id, username=u.username)
    db.commit()
    return PasswordResetOut(user=user_out(_user(db, u.id)), temporary_password=temp)
