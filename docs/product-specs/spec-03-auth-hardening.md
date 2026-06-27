# Spec 03 — Auth Hardening: refresh tokens, secret guard, server-side logout

## Goal

Make the JWT session secure and long-lived for real use: a short-lived access token
backed by a revocable refresh token (so a user is not kicked out every hour), a startup
guard that refuses to run in production with the insecure default secret, and a server-side
logout that actually invalidates a session instead of only clearing the browser.

## Screens

- **Login** (existing) — unchanged in layout; on success the session now survives access-token
  expiry silently (no surprise bounce to Login mid-use).
- **Dashboard** (existing) — its **Logout** action now ends the session server-side, not just
  client-side. No new screen is introduced.

## Features

- **Short access token + refresh token.** Access token lifetime cut to ~15 minutes; a
  long-lived (~7 day) refresh token is issued in an **httpOnly cookie** and used to mint new
  access tokens without re-login.
- **`POST /api/auth/refresh`** — exchanges a valid refresh cookie for a fresh access token,
  **rotating** the refresh token (old one is invalidated) to prevent replay.
- **`POST /api/auth/logout`** — revokes the current refresh token server-side and clears the
  cookie.
- **Server-side refresh-token store** — refresh tokens are persisted (hashed) so they can be
  revoked; logout and rotation operate on this store.
- **Hard-revoke via `token_version`** — a per-user counter embedded in the access token;
  bumping it invalidates every outstanding access token immediately (logout-all / account lock).
- **Production secret guard** — the app fails to start in production if `JWT_SECRET` is unset,
  empty, the known insecure default, or shorter than 32 characters.

## Logic / flow

> Behavioural happy path. The 🔨 Generator builds to this order; the 🔍 Evaluator walks it.

1. User logs in (`POST /api/auth/login`) → backend returns a short-lived **access token** in the
   body **and** sets a **refresh token** in an httpOnly cookie scoped to `/api/auth`.
2. Frontend holds the access token in memory and calls the API with
   `Authorization: Bearer <access>`.
3. Access token expires → the next API call returns `401`. The frontend calls
   `POST /api/auth/refresh` **once** (the cookie rides along automatically), gets a new access
   token, and **retries the original request** transparently — the user notices nothing.
4. On refresh, the backend validates the stored refresh token, **rotates** it (issues a new one,
   revokes the old), and updates the cookie.
5. On full page reload, the frontend has no in-memory token, so it calls `POST /api/auth/refresh`
   at startup to restore the session from the cookie; success → Dashboard, failure → Login.
6. **Logout** calls `POST /api/auth/logout` → backend revokes the refresh token and clears the
   cookie → frontend drops the in-memory access token and returns to Login.
7. **Logout-all / lock**: bumping the user's `token_version` makes every existing access token
   fail the next request immediately; the affected user is routed to Login.

## System statuses

- **Access expired but session still valid** — `401` on an API call triggers a single silent
  refresh + retry; the user is NOT shown an error or bounced to Login.
- **Refresh expired / revoked** — `/api/auth/refresh` returns `401`; the frontend treats the
  session as ended and shows Login (never a blank/frozen screen).
- **Account locked mid-session** (`is_active=false` or `token_version` bumped) — the next request
  yields `401`/`403` and the user is routed to Login with a clear message.
- **Backend unreachable during refresh** — plain-language error with a retry affordance; the
  in-memory access token is not discarded on a mere network blip.
- **Misconfigured production secret** — the backend refuses to start and logs a clear, actionable
  message (which env var to set); it does not boot insecurely.

## Edge cases

- **Refresh-token replay** — presenting an already-rotated (old) refresh token → `401` and, as a
  safety response, the token family is revoked. No new access token is issued.
- **Refresh storm** — many concurrent `401`s must trigger at most one in-flight `/refresh`
  (shared promise); queued requests retry after it resolves. No duplicate refresh calls.
- **Logout then use a stale tab** — a second tab still holding an access token: its next call
  fails at access expiry (≤15 min) and cannot refresh (cookie revoked) → routed to Login.
- **Tampered / garbage refresh cookie** — treated as unauthenticated (`401`), never a 500.
- **Clock skew / exactly-at-expiry token** — handled as expired (fail closed), not accepted.
- **CORS + credentials** — the browser only sends the cookie when the API client uses
  `credentials: "include"` and the backend echoes a specific origin (not `*`) with
  `Allow-Credentials: true`.

## Acceptance criteria

> Per-endpoint / per-screen, observable assertions. API criteria are `pytest` checks on
> status + cookie + body; UI criteria are browser assertions (snapshot/text/state via the
> browser validation loop). All confirmed on top of green `./init.sh` / `./init.ps1` — never as
> a replacement. Every Logic/flow step, System status, and Edge case above maps to a line here.

### Baseline

- `init.ps1` / `init.sh` pass: `python -m pytest` (incl. new auth-hardening tests) + `compileall`.
- `docs/DB_SCHEMA.md` documents every new table/column (refresh-token store, `users.token_version`)
  and the schema-doc guard test passes.
- Console is clean of uncaught errors across every UI journey below; only the expected
  `login` / `refresh` / `logout` / `me` calls fire, each with the asserted status.

### Startup secret guard (config / boot)

- `APP_ENV=production` + `JWT_SECRET` **unset** → process exits non-zero with a message naming
  `JWT_SECRET`; the server does not bind its port.
- `APP_ENV=production` + `JWT_SECRET` = the known default `dev-insecure-secret-change-me` → same
  fail-fast exit.
- `APP_ENV=production` + `JWT_SECRET` shorter than 32 chars → same fail-fast exit.
- `APP_ENV=production` + a strong (≥32-char) secret → boots normally.
- `APP_ENV` unset/`development` → boots with the existing default (zero-config local), optionally
  logging a one-line warning.

### `POST /api/auth/login`

- Valid seeded creds → `200`, body has a non-empty `access_token` whose lifetime is ~15 minutes
  (configurable), **and** a `Set-Cookie` for the refresh token with `HttpOnly`, `SameSite`,
  `Path=/api/auth`, and `Secure` when `APP_ENV=production`.
- The refresh token is persisted in the store (one active row for the user) as a **hash**, never
  in plaintext.
- Wrong creds → `401`, no `access_token`, no refresh `Set-Cookie`.

### `POST /api/auth/refresh`

- Valid refresh cookie → `200` + a new `access_token`, **and** a `Set-Cookie` whose refresh value
  differs from the one sent (rotation); the previous refresh row is marked revoked.
- A rotated (previous) refresh token reused → `401`, no `access_token`; as a theft signal the
  token family is revoked (subsequent refreshes with any sibling also `401`).
- Missing / malformed / tampered refresh cookie → `401` (never `500`).
- Expired refresh token → `401`.
- Refresh whose user has `is_active=false` → `401`/`403` (locked accounts cannot renew).

### `POST /api/auth/logout`

- With a valid refresh cookie → `204`; the refresh row is revoked and the response clears the
  cookie (`Max-Age=0` / expired).
- After logout, `POST /api/auth/refresh` with the old cookie → `401`.
- Logout with no/invalid cookie → still `204` (idempotent), no error.

### Access-token check (`GET /api/auth/me` and any protected route)

- Expired access token → `401` (`pytest` mints one past expiry).
- Access token whose embedded `token_version` ≠ the user's current `token_version` → `401`
  (bump the counter, prove the old token is rejected on the next request).
- A locked user (`is_active=false`) with an otherwise-valid access token → `403` (unchanged).

### UI — silent refresh (no surprise logout)

- Drive the app, let the access token pass expiry, then perform an action → the user **stays on
  the Dashboard**; the network log shows exactly one `/refresh` (200) followed by the retried
  original call; the Login form does not reappear.
- Many concurrent calls hitting an expired token → at most **one** `/refresh` in the network log
  (shared in-flight refresh), then all retries succeed.

### UI — reload restores via cookie

- After login, a full page reload lands on the **Dashboard** via a startup `/refresh` (200); there
  is **no** bearer token stored in `localStorage` (refresh lives only in the httpOnly cookie).
- Reload after the refresh cookie is gone/expired → lands on **Login**, not a blank screen.

### UI — logout ends the session

- Click Logout → returns to **Login**; the network log shows a `/logout` (204).
- A subsequent reload stays on **Login** (startup `/refresh` returns 401).
- A second tab still holding an access token: its next action after access expiry routes to Login
  (cannot refresh — cookie revoked).

## Out-of-scope

- "Remember me" duration choices, device/session management UI (listing or revoking individual
  devices beyond logout / logout-all).
- OAuth / social login, password reset, email verification, self-registration.
- Moving token storage to a third-party identity provider.
- A distributed denylist (Redis) for access tokens — the `token_version` check covers hard-revoke
  without extra infrastructure this spec.
- Switching the DB migration strategy to Alembic (the refresh-token table lands via the existing
  `create_all` + seed; note the "drop dev.db to pick up new schema" caveat).

## Failure states

- **Refresh expired/revoked** → frontend routes to Login with "Phiên đã hết hạn, đăng nhập lại";
  no duplicate side effects.
- **Backend unreachable during refresh** → plain-language error + explicit Retry; the access
  token in memory is kept across a transient network failure.
- **Production boot with insecure/missing secret** → process exits with a clear message naming the
  env var to set; it never serves traffic with the default secret.
- **Replay / token theft signal** (rotated token reused) → the refresh-token family is revoked,
  forcing a fresh login; logged for audit.
