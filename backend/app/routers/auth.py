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
    FILE_COOKIE,
    FILE_COOKIE_PATH,
    CurrentUser,
    get_auth_service,
    get_authorization_service,
    get_profile_service,
    get_refresh_service,
    get_refresh_token_repository,
)
from ..repositories.refresh_token_repo import RefreshTokenRepository
from ..schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    PermissionsOut,
    ProfileOut,
    TokenResponse,
    UserOut,
)
from ..security import create_access_token, create_file_token
from ..services.auth_service import AuthError, AuthService, PasswordChangeError
from ..services.profile_service import ProfileService
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


def _set_file_cookie(response: Response, user) -> None:
    """Cookie cho `<img src>` đọc /api/files (không gắn được header Bearer).

    Cùng vòng đời với refresh cookie để ảnh không chết giữa phiên; `tv` bên trong khiến
    đổi-mật-khẩu / logout-all giết luôn nó.
    """
    response.set_cookie(
        key=FILE_COOKIE,
        value=create_file_token(subject=str(user.id), token_version=user.token_version),
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=FILE_COOKIE_PATH,
    )


def _clear_file_cookie(response: Response) -> None:
    response.delete_cookie(FILE_COOKIE, path=FILE_COOKIE_PATH)


def _issue_access(user) -> str:
    return create_access_token(subject=str(user.id), token_version=user.token_version)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
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
    _set_refresh_cookie(response, refresh.issue(user, user_agent=request.headers.get("user-agent")))
    _set_file_cookie(response, user)
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
        new_raw, user = refresh.rotate(raw, user_agent=request.headers.get("user-agent"))
    except RefreshError:
        _clear_refresh_cookie(response)
        _clear_file_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from None
    _set_refresh_cookie(response, new_raw)
    _set_file_cookie(response, user)
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
    _clear_file_cookie(response)
    return response


@router.get("/me", response_model=ProfileOut)
def me(
    current_user: CurrentUser,
    profiles: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileOut:
    # Enriched profile (department/role names + created_at) for the account panel (spec-04).
    return ProfileOut.model_validate(profiles.get_profile(current_user))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
) -> Response:
    """Self-service password change (spec-04). Verifies the current password, stores the new
    hash + bumps token_version (kills access tokens), and revokes every refresh token so all
    sessions end. The frontend then returns to Login. Cookie clearing is handled client-side
    by the forced re-login; we also clear it here for good measure."""
    try:
        auth.change_password(current_user, payload.current_password, payload.new_password)
    except PasswordChangeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    refresh_tokens.revoke_all_for_user(current_user.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    _clear_file_cookie(response)
    return response


@router.get("/permissions", response_model=PermissionsOut)
def my_permissions(
    current_user: CurrentUser,
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> PermissionsOut:
    return PermissionsOut(
        modules=authz.readable_modules(current_user),
        permissions=authz.capabilities(current_user),
    )
