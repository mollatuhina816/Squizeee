# Authentication and persistent sessions

`POST /api/auth/login`, `/api/auth/refresh`, and `/api/auth/logout` also exist
under `/api/v1/auth/` for the existing UI. Send the configured `APP_ORIGIN` in
the `Origin` header on all three endpoints; login and refresh are rate limited
through Redis. Responses have `Cache-Control: no-store`.

Login accepts `email`, `password`, and an optional boolean `remember_me`
(default `false`). The response includes the existing account fields plus
`access_token`, `token_type: "bearer"`, and `expires_in` (86,400 seconds for
teachers; 900 seconds for students).
Use `Authorization: Bearer <access_token>` for API requests. The existing
`quizeee_access` HttpOnly cookie remains available for the current browser UI.
JWT validation pins HS256, issuer, audience, token type, expiry, user, and the
persisted session. Revocation therefore also invalidates outstanding access JWTs.

The `refresh_token` cookie is always HttpOnly, Secure, SameSite=Lax, host-only,
and uses `/` so both endpoint prefixes work. HTTPS is required for deployments;
modern browsers also support Secure cookies on localhost. Non-browser local
clients must use HTTPS or explicitly manage cookies when testing HTTP.

- `remember_me: true`: persistent refresh cookie, with a maximum lifetime of
  30 days from login. Rotation never extends this absolute deadline.
- `remember_me: false`: refresh cookie has no Max-Age or Expires. Browsers
  determine session-cookie lifetime, and some restore them with restored tabs.
  The database still enforces a 30-day upper bound.

Refresh takes no JSON body. Send cookies with the request. Each successful
refresh consumes the old secret, sets a replacement cookie, and returns a new
access token. The refresh secret is a cryptographically random opaque value;
only its SHA-256 digest is stored in PostgreSQL. Token history belongs to an
AuthSession family, which is locked with SELECT FOR UPDATE during rotation
and logout. Replay of any consumed secret revokes the family, including its
current refresh token and every access JWT. Unknown random secrets cannot
revoke another user's session. Other logins remain independent.

Clients must serialize refresh requests, including across tabs. A duplicate
refresh is treated as reuse and requires signing in again. After an access
token expires, call refresh once and retry the request once. The workspace,
editor, presenter, and host WebSocket ticket requests use `authFetch` to do
this automatically, coordinating browser tabs with Web Locks where available.
The backend does not implicitly refresh authenticated requests. Keep JSON access tokens
in memory, and never store refresh secrets in JavaScript storage.

Logout accepts a refresh cookie even after the access token expires, or a valid
access credential for legacy sessions. It revokes the family, clears the auth
and guest-profile cookies, and is idempotent. Consumed token digests are retained
for replay detection. Expired sessions can be deleted by scheduled maintenance;
their token rows cascade-delete. Do not delete rotation history for live sessions.

Apply the migration with `python -m alembic upgrade head` and restart the API.
Run migrations as the database table owner. When the runtime account is a
separate restricted role, grant it SELECT, INSERT, UPDATE, DELETE on the new
`refresh_tokens` table after migration.
Existing access-only sessions remain valid until their original expiration;
users must sign in again to receive a refresh cookie. The default access-token
lifetime for students is 15 minutes; `ACCESS_MINUTES` can shorten it but cannot
exceed 15. Teacher tokens last 24 hours by default; `TEACHER_ACCESS_HOURS` can
shorten this but cannot exceed 24. Login and refresh both apply these lifetimes;
existing tokens acquire the new lifetime on their next refresh or login.

Run unit/API checks with `python -m pytest`. To additionally run real concurrent
PostgreSQL checks, set `QUIZEEE_TEST_POSTGRES_URL` to a test database URL and run
`python -m pytest tests/test_refresh_postgres.py`. These checks create and remove
a uniquely named schema and require schema-creation permission.

The rotation and family-revocation behavior follows
[RFC 9700, section 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).
