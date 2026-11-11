"""Seed the admin and the branch managers.

Run inside the API container (the database is the Compose ``mysql`` service):

    docker compose exec api python -m app.seed_users                 # prompts for passwords
    docker compose exec api python -m app.seed_users --generate      # random passwords
    ADMIN_PASSWORD=... DEMO_MANAGER_PASSWORD=... \\
        docker compose exec -e ADMIN_PASSWORD -e DEMO_MANAGER_PASSWORD api python -m app.seed_users
    make seed-users ARGS="--generate --reset-passwords"

Passwords are never accepted as command-line arguments (they would end up in the shell
history and the process list). They come from ADMIN_PASSWORD / DEMO_MANAGER_PASSWORD, from
a hidden prompt, or are generated (``--generate``). The script is idempotent: existing users
are left alone unless ``--reset-passwords`` is given. It prints only the credentials it set,
once; they are not stored anywhere in plain text.

The API's startup seeding (``app.bootstrap``) uses the same functions.
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import string
import sys
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import audit, hash_password, utcnow
from app.config import Settings, get_settings
from app.storage.models import ROLE_ADMIN, ROLE_MANAGER, Branch, Upload, User

MIN_PASSWORD = 8

# One branch manager per branch.
BRANCH_MANAGERS: dict[str, str] = {
    "Haifa": "manager.haifa",
    "Rishon LeZion": "manager.rishon",
    "Tel Aviv": "manager.telaviv",
    "Jerusalem": "manager.jerusalem",
    "Be'er Sheva": "manager.beersheva",
    "Netanya": "manager.netanya",
    "Petah Tikva": "manager.petah",
    "Ashdod": "manager.ashdod",
    "Herzliya": "manager.herzliya",
    "Beit Shemesh": "manager.beitshemesh",
    "Kfar Saba": "manager.kfarsaba",
    "Rehovot": "manager.rehovot",
}


@dataclass
class SeedResult:
    username: str
    full_name: str
    role: str
    branch: str | None
    action: str  # "created" | "password reset" | "unchanged" | "skipped: <why>"
    password: str | None = None  # only when this run set it


def generate_password(length: int = 14) -> str:
    """Random, readable (no 0/O/1/l/I), with at least one digit."""
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def ensure_user(
    db: Session,
    *,
    username: str,
    full_name: str,
    role: str,
    branch: Branch | None,
    password: str,
    reset_password: bool = False,
    must_change_password: bool = False,
) -> SeedResult:
    """Create the user if missing; reset the password only when asked. Never logs it."""
    username = username.strip().lower()
    branch_name = branch.name if branch else None
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            branch_id=branch.id if branch else None,
            is_active=True,
            must_change_password=must_change_password,
            created_at=utcnow(),
        )
        db.add(user)
        db.flush()
        audit(db, None, "user.created", "user", user.id, username=username, branch=branch_name,
              source="seed_users")  # fmt: skip
        return SeedResult(username, full_name, role, branch_name, "created", password)
    if reset_password:
        user.password_hash = hash_password(password)
        user.must_change_password = must_change_password
        user.is_active = True
        audit(db, None, "user.password_reset", "user", user.id, username=username,
              source="seed_users")  # fmt: skip
        return SeedResult(username, user.full_name, user.role, branch_name, "password reset",
                          password)  # fmt: skip
    return SeedResult(username, user.full_name, user.role, branch_name, "unchanged")


def seed_admin_user(
    db: Session,
    settings: Settings,
    password: str,
    *,
    reset_password: bool = False,
) -> SeedResult:
    res = ensure_user(
        db,
        username=settings.admin_username,
        full_name=settings.admin_full_name,
        role=ROLE_ADMIN,
        branch=None,
        password=password,
        reset_password=reset_password,
    )
    admin = db.scalar(select(User).where(User.username == res.username))
    assert admin is not None
    # Uploads made before users existed belong to the admin.
    db.execute(update(Upload).where(Upload.uploaded_by.is_(None)).values(uploaded_by=admin.id))
    return res


def seed_branch_managers(
    db: Session,
    password_for: dict[str, str] | str,
    *,
    reset_password: bool = False,
    must_change_password: bool = False,
) -> list[SeedResult]:
    """One manager per branch in BRANCH_MANAGERS. ``password_for`` is one shared password
    or a {username: password} map. Branches not in the registry are skipped."""
    out = []
    for branch_name, username in BRANCH_MANAGERS.items():
        b = db.scalar(select(Branch).where(Branch.name == branch_name))
        if b is None:
            out.append(SeedResult(username, "", ROLE_MANAGER, branch_name,
                                  "skipped: branch not in the registry yet"))  # fmt: skip
            continue
        pw = password_for if isinstance(password_for, str) else password_for[username]
        out.append(
            ensure_user(
                db,
                username=username,
                full_name=f"{branch_name} manager",
                role=ROLE_MANAGER,
                branch=b,
                password=pw,
                reset_password=reset_password,
                must_change_password=must_change_password,
            )
        )
    return out


# ---------- CLI ----------


def _password(env: str, label: str, args: argparse.Namespace) -> str:
    value = os.environ.get(env)
    if value:
        return value
    if args.generate:
        return generate_password()
    if not sys.stdin.isatty():
        raise SystemExit(
            f"{env} is not set and there is no terminal to prompt on. Set {env}, or use --generate."
        )
    while True:
        first = getpass.getpass(f"{label} password (min {MIN_PASSWORD} chars): ")
        if len(first) < MIN_PASSWORD:
            print(f"  Too short: at least {MIN_PASSWORD} characters.")
            continue
        if getpass.getpass(f"Repeat {label.lower()} password: ") != first:
            print("  The two passwords do not match.")
            continue
        return first


def _print_table(results: list[SeedResult]) -> None:
    rows = [("USERNAME", "ROLE", "BRANCH", "RESULT", "PASSWORD")] + [
        (
            r.username,
            "admin" if r.role == ROLE_ADMIN else "branch manager",
            r.branch or "all branches",
            r.action,
            r.password or "(not changed)",
        )
        for r in results
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    for i, row in enumerate(rows):
        print("  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row)).rstrip())
        if i == 0:
            print("  ".join("-" * w for w in widths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed_users",
        description="Create the admin and one branch manager per branch.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="generate random passwords for anything not set in the environment",
    )
    parser.add_argument(
        "--per-manager",
        action="store_true",
        help="with --generate: a different password for each manager (default: one shared)",
    )
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="also set new passwords for users that already exist",
    )
    parser.add_argument(
        "--must-change",
        action="store_true",
        help="managers must choose their own password at first sign-in",
    )
    parser.add_argument("--admin-only", action="store_true", help="seed only the admin")
    parser.add_argument("--managers-only", action="store_true", help="seed only the managers")
    parser.add_argument(
        "--format",
        choices=("table", "env"),
        default="table",
        help="'env' prints ADMIN_PASSWORD= / DEMO_MANAGER_PASSWORD= lines for a .env file",
    )
    args = parser.parse_args(argv)
    if args.admin_only and args.managers_only:
        parser.error("--admin-only and --managers-only are mutually exclusive")
    if args.per_manager and not args.generate:
        parser.error("--per-manager needs --generate")
    if args.per_manager and args.format == "env":
        parser.error("--format env needs one shared manager password (drop --per-manager)")

    settings = get_settings()
    from app.storage.session import get_sessionmaker  # after argparse, so --help needs no DB

    results: list[SeedResult] = []
    admin_pw = manager_pw = None
    with get_sessionmaker()() as db:
        if not args.managers_only:
            admin_pw = _password("ADMIN_PASSWORD", "Admin", args)
            if len(admin_pw) < MIN_PASSWORD:
                raise SystemExit(f"ADMIN_PASSWORD must be at least {MIN_PASSWORD} characters.")
            results.append(
                seed_admin_user(db, settings, admin_pw, reset_password=args.reset_passwords)
            )
        if not args.admin_only:
            if args.per_manager and not os.environ.get("DEMO_MANAGER_PASSWORD"):
                pw_for: dict[str, str] | str = {
                    u: generate_password() for u in BRANCH_MANAGERS.values()
                }
            else:
                manager_pw = _password("DEMO_MANAGER_PASSWORD", "Branch manager", args)
                if len(manager_pw) < MIN_PASSWORD:
                    raise SystemExit(
                        f"DEMO_MANAGER_PASSWORD must be at least {MIN_PASSWORD} characters."
                    )
                pw_for = manager_pw
            results += seed_branch_managers(
                db,
                pw_for,
                reset_password=args.reset_passwords,
                must_change_password=args.must_change,
            )
        db.commit()

    if args.format == "env":
        set_admin = any(r.role == ROLE_ADMIN and r.password for r in results)
        set_mgr = any(r.role == ROLE_MANAGER and r.password for r in results)
        if set_admin:
            print(f"ADMIN_PASSWORD={admin_pw}")
        if set_mgr:
            print(f"DEMO_MANAGER_PASSWORD={manager_pw}")
        if not (set_admin or set_mgr):
            print("# nothing changed (users exist; use --reset-passwords to set new ones)")
        return 0

    _print_table(results)
    changed = sum(1 for r in results if r.password)
    print()
    if changed:
        print(f"{changed} account(s) set. These passwords are shown once and are not stored.")
    else:
        print("Nothing changed: the users already exist. Use --reset-passwords to set new ones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
