"""FastAPI dependencies: DB sessions and authentication (HTTP + WebSocket)."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from . import security, users
from .db import get_session
from .models import User
from .security import TokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def _user_from_token(token: str, session: Session) -> Optional[User]:
    try:
        payload = security.decode_token(token)
        return users.get_by_id(session, int(payload["sub"]))
    except (TokenError, KeyError, ValueError):
        return None


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the bearer token to a user, or raise 401."""
    user = _user_from_token(token, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def user_from_ws_token(token: Optional[str], session: Session) -> Optional[User]:
    """Resolve a token passed as a WebSocket query parameter (no HTTP 401)."""
    if not token:
        return None
    return _user_from_token(token, session)
