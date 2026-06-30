"""Auth routes: login + refresh + logout + current-user.

Thin HTTP shell over AuthService / RefreshTokenService. The refresh token lives in an
httpOnly cookie (spec-03): the access token is returned in the body, the refresh token is
set/rotated/cleared as a cookie scoped to this router's path.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..config import settings
from ..deps import (
    CurrentUser,
    get_auth_service,
    get_authorization_service,
    get_refresh_service,
)
from ..schemas.auth import LoginRequest, PermissionsOut, TokenResponse, UserOut
from ..security import create_access_token
from ..services.auth_service import AuthError, AuthService
from ..services.rbac_service import AuthorizationService
from ..services.refresh_service import RefreshError, RefreshTokenService

router = APIRouter(prefix="/api/auth", tags=["auth"])

# The refresh cookie is scoped to /api/auth so it is only ever sent to these endpoints.
REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,  # HTTPS-only in production
        samesite="lax",
        path=COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)


def _issue_access(user) -> str:
    return create_access_token(subject=str(user.id), token_version=user.token_version)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    refresh: Annotated[RefreshTokenService, Depends(get_refresh_service)],
) -> TokenResponse:
    try:
        token, user = auth.login(payload.username, payload.password)
    except AuthError:
        # Generic message — never reveal whether the username exists (spec-0001).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không đúng",
        ) from None
    _set_refresh_cookie(response, refresh.issue(user))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    request: Request,
    response: Response,
    refresh: Annotated[RefreshTokenService, Depends(get_refresh_service)],
) -> TokenResponse:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        new_raw, user = refresh.rotate(raw)
    except RefreshError:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from None
    _set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=_issue_access(user), user=UserOut.model_validate(user))


@router.post("/logout", response_class=Response)
def logout(
    request: Request,
    refresh: Annotated[RefreshTokenService, Depends(get_refresh_service)],
) -> Response:
    # Idempotent: revoke the presented refresh token (if any) and clear the cookie.
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        refresh.revoke(raw)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/permissions", response_model=PermissionsOut)
def my_permissions(
    current_user: CurrentUser,
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> PermissionsOut:
    return PermissionsOut(modules=authz.readable_modules(current_user))
