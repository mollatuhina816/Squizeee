# Verification record

Milestone checked 23 September 2026.

## Passed

- 41 backend tests. Covers registration/password hashing, JWT tampering/revocation, origin validation, overposting, cross-tenant access, department scope, role escalation restrictions, Faculty Lite policy ceilings, stale presentation edits, question validation/scoring, duplicate/late answers, frozen live snapshots, import preview/commit, formula rejection/escaping and four export signatures/readability.
- Next.js optimized build with TypeScript checking. Routes include workspace, editor, live presenter, participant join, bank and analytics.
- Alembic migrations applied to an isolated SQLite test database; `alembic check` reports no new upgrade operations.
- PostgreSQL migration SQL generated in offline mode (`docs/postgresql-schema.sql`); this is a dialect compilation check, not execution against a PostgreSQL server.
- Browser smoke flow against an isolated disposable fixture: create organization → create presentation → open editor → add/edit/save MCQ → start session → show join code/QR → join as student in a second tab → open question → submit answer → receive acknowledgement → see response count and score in presenter view.
- Login and participant screens visually inspected. This is limited visual QA, not a full responsive/accessibility audit.

## Important limits

- PostgreSQL/Redis/Docker were unavailable as running project services. PostgreSQL row locks, unique-code races, Redis Pub/Sub, socket ticket redemption and Celery delivery have not been integration-tested here.
- Browser smoke fixture uses SQLite and bypasses rate limiting/notifications only in `work/preview.py`, outside the deliverable. Presenter and participant views recovered via polling. This does not verify real WebSocket push.
- No load, penetration, production infrastructure, email, payment, AI, backup/restore or multi-node tests have passed because those environments/modules are not present.
- Test dependencies emitted two deprecation warnings from the FastAPI/Starlette HTTPX test transport. No failing tests.
- No production claim should be made from this record. See README for unimplemented scope.

## Next verification gates

1. Run migrations up/down/up and integration tests against PostgreSQL; test concurrent submissions and edit conflicts.
2. Run Redis and verify one-use socket ticket expiry/reuse, origin rejection, Pub/Sub fan-out, reconnect and cache outages.
3. Replace disposable browser fixture with the real services and repeat complete presenter/participant flows on desktop/mobile.
4. Complete missing modules in the specified order and extend tests around each authorization boundary.
5. Agree on concurrency targets, run sustained load tests, and resolve bottlenecks before production release.
