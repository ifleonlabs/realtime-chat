"""User service: registration and authentication."""

from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from . import security
from .models import User
from .schemas import UserCreate


class AuthError(Exception):
    """Raised for registration/authentication problems."""


def get_by_username(session: Session, username: str) -> Optional[User]:
    return session.exec(select(User).where(User.username == username)).first()


def get_by_id(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def register(session: Session, data: UserCreate) -> User:
    if get_by_username(session, data.username):
        raise AuthError("That username is already taken.")
    user = User(
        username=data.username,
        hashed_password=security.hash_password(data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, username: str, password: str) -> User:
    user = get_by_username(session, username)
    if user is None:
        # Run a dummy verify to reduce timing differences.
        security.verify_password(password, security.hash_password("placeholder"))
        raise AuthError("Incorrect username or password.")
    if not security.verify_password(password, user.hashed_password):
        raise AuthError("Incorrect username or password.")
    return user
