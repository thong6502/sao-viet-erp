# Spec 01 — Foundation & Login

## Goal

Stand up the runnable app skeleton (React + Vite + TypeScript frontend, FastAPI
backend, PostgreSQL via Docker) and let a seeded user log in with email + password,
receive a JWT, and reach a protected page.

## Screens

- **Login** — email + password form, submit, inline error on bad credentials.
- **Dashboard** (protected) — minimal landed page showing the logged-in user's
  identity and a Logout action; only reachable when authenticated.

## Features

- Project skeleton that runs and verifies green (`init.sh` / `init.ps1`).
- PostgreSQL running in Docker (compose), reached by the backend via `DATABASE_URL`.
- Seeded admin user (no self-registration this spec).
- `POST /api/auth/login` issuing a JWT bearer token.
- `GET /api/auth/me` returning the current user for a valid token.
- Frontend login → token persisted → protected Dashboard + Logout.

## Logic / flow

1. User opens the app unauthenticated → sees the **Login** screen.
2. User enters email + password → submits.
3. Frontend (via the API client only) calls `POST /api/auth/login`.
4. Backend verifies the password hash and returns `{ access_token, token_type, user }`.
5. Frontend stores the token, then renders the protected **Dashboard** for that user.
6. On reload, the frontend calls `GET /api/auth/me` with the stored token to restore
   the session; an invalid/expired token routes back to Login.
7. Logout clears the token and returns to Login.

## System statuses

- **Session expired / not authenticated** — a missing/invalid/expired token yields
  `401`; the frontend shows Login (never a blank or frozen screen).
- **Backend error / unreachable** — a 5xx or network failure surfaces a plain-language
  error with a retry affordance, not a raw stack or JSON.

## Edge cases

- Empty email or empty password → client-side validation blocks submit with a field message.
- Wrong email or wrong password → single generic "Invalid email or password" (no user
  enumeration), credentials field cleared of password.
- Very long / unexpected-character input → handled as data, never interpolated into SQL
  (parameterized queries / ORM only).
- Double-submit (rapid clicks) → submit button disabled and shows a loading state while
  the request is in flight; no duplicate login calls.

## Acceptance criteria

> UI criteria are observable browser assertions (snapshot/text/state) confirmed on top of
> green `./init.sh` / `./init.ps1`.

- `init.ps1` / `init.sh` pass: `python -m pytest` (incl. backend auth tests) + `compileall`.
- `docker compose up db` starts PostgreSQL; the backend connects via `DATABASE_URL` and
  serves on its port.
- `POST /api/auth/login` with the seeded credentials returns `200` and a non-empty
  `access_token`; with wrong credentials returns `401` and no token.
- `GET /api/auth/me` returns `200` + the user for a valid `Authorization: Bearer <token>`,
  and `401` for a missing/garbage token.
- Login screen: snapshot shows email + password fields and a submit button; submitting
  empty fields shows a validation message and fires no network call.
- Successful login: the Dashboard snapshot shows the logged-in user's email; the login
  form is gone.
- Wrong credentials: an error message with text "Invalid email or password" appears; the
  user stays on Login.
- Reload after login keeps the user on the Dashboard (token restored via `/me`).
- Logout returns to the Login screen and a subsequent reload stays on Login.
- Console is clean of uncaught errors across the journey; only the expected
  `login` / `me` network calls fire with expected statuses.

## Out-of-scope

- Self-registration / sign-up, password reset, email verification.
- Refresh tokens, roles/permissions (RBAC), "remember me", OAuth/social login.
- Alembic migrations (this spec uses `create_all` + seed; migrations land later).
- Any feature screen beyond the minimal protected Dashboard.

## Failure states

- Invalid credentials → inline `--signal` error "Invalid email or password"; user retries.
- Backend unreachable / 5xx → plain-language error + explicit Retry; no duplicate side
  effects on retry.
- Expired/invalid stored token on reload → silently routed to Login (treated as logged out).
