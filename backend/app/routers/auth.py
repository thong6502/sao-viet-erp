"""Auth routes: login + current-user. Thin HTTP shell over AuthService."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import CurrentUser, get_auth_service, get_authorization_service
from ..schemas.auth import LoginRequest, PermissionsOut, TokenResponse, UserOut
from ..services.auth_service import AuthError, AuthService
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        token, user = auth.login(payload.email, payload.password)
    except AuthError:
        # Generic message — never reveal whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/permissions", response_model=PermissionsOut)
def my_permissions(
    current_user: CurrentUser,
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> PermissionsOut:
    return PermissionsOut(modules=authz.readable_modules(current_user))
