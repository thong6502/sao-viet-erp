"""FastAPI dependency providers (the composition root for each request).

Wires DB session -> repository -> service, and resolves the bearer token into the
current user. Auth enters here as an explicit dependency boundary, not by reaching
across layers (docs/ARCHITECTURE.md).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models.user import User
from .repositories.user_repo import UserRepository
from .security import decode_access_token
from .services.auth_service import AuthError, AuthService

# auto_error=False so we can return our own 401 shape for missing/invalid tokens.
_bearer = HTTPBearer(auto_error=False)


def get_user_repository(db: Annotated[Session, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(users)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or not creds.credentials:
        raise unauthorized

    claims = decode_access_token(creds.credentials)
    if claims is None:
        raise unauthorized
    try:
        return auth.user_from_token_subject(claims.get("sub"))
    except AuthError:
        raise unauthorized from None


CurrentUser = Annotated[User, Depends(get_current_user)]
