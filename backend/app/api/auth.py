"""Sign-in (OAuth2 password flow), current user, change own password.

No public sign-up and no e-mailed password reset (that would need an SMTP account): Summer
resets passwords from the Users screen. Logout is client-side (the token is dropped).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import (
    _unauthorized,
    audit,
    authenticate,
    create_access_token,
    current_user,
    hash_password,
    verify_password,
)
from app.config import Settings, get_settings
from app.storage.models import User
from app.storage.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

MIN_PASSWORD = 8


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool


class MeOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    branch_id: int | None
    branch: str | None
    must_change_password: bool


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD, max_length=72)


def me_out(u: User) -> MeOut:
    return MeOut(
        id=u.id,
        username=u.username,
        full_name=u.full_name,
        role=u.role,
        branch_id=u.branch_id,
        branch=u.branch.name if u.branch else None,
        must_change_password=u.must_change_password,
    )


@router.post("/login", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    user = authenticate(db, form.username, form.password)
    if user is None:
        # Same message for unknown user, wrong password and deactivated account.
        raise _unauthorized("Wrong username or password.")
    return TokenOut(
        access_token=create_access_token(user, settings),
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)) -> MeOut:
    return me_out(user)


@router.post("/change-password", response_model=MeOut)
def change_password(
    body: ChangePasswordIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MeOut:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is not correct.")
    if body.new_password == body.current_password:
        raise HTTPException(400, "Choose a password different from the current one.")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit(db, user, "user.password_changed", "user", user.id, username=user.username)
    db.commit()
    db.refresh(user)
    return me_out(user)
