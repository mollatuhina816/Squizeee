# Quizeee codebase audit

**Scope:** Read-only review of the current working tree. This report describes
the code that was present at audit time, not necessarily a released or deployed
version. The worktree already contained uncommitted changes. Secret values were
not inspected, and no penetration or load test was run.

## 1. Project overview

| Area | What is implemented |
|---|---|
| Project | **Quizeee**, a quiz and interactive-presentation application. |
| Frontend | Next.js App Router, React, and TypeScript; package management with pnpm. Key app entry: [`frontend/app/page.tsx`](../frontend/app/page.tsx). |
| Backend | Python, FastAPI, Pydantic, and SQLAlchemy; key API entry: [`backend/app/main.py`](../backend/app/main.py). |
| Database | PostgreSQL, with SQLAlchemy models and Alembic migrations. |
| Redis | Used for rate limits, live-event pub/sub, WebSocket tickets, and as the Celery broker/result backend. It is not a general application cache in the inspected code. |
| Realtime | WebSockets for live sessions, with Redis pub/sub. REST snapshots are also used for recovery/polling. |
| Background jobs | Celery is configured, but the only registered Celery task is a health task. Scheduled-quiz expiry is instead checked by a loop in the API process. |
| AI | OpenAI or Gemini for question generation. Gemini is also used in document-import interpretation and answer-suggestion flows. |
| Deployment | Dockerfiles and Docker Compose define PostgreSQL, Redis, migration, API, worker, and web services. Compose describes itself as a local-development baseline, not a production deployment. |
| Package managers | pnpm for the frontend; pip/Python dependency manifests and lock file for the backend; Alembic for schema migrations. |
| Main entry points | Frontend routes under [`frontend/app/`](../frontend/app/); FastAPI app in [`backend/app/main.py`](../backend/app/main.py); Celery app in [`backend/app/worker.py`](../backend/app/worker.py); deployment in [`compose.yaml`](../compose.yaml). |

**High-level structure:** `backend/app/` contains application code,
`backend/migrations/` schema history, and `backend/tests/` tests;
`frontend/app/` contains route pages and UI components, and `frontend/tests/`
contains helper tests. `docs/` contains feature and schema documentation. Root
configuration includes Compose, environment examples, and local run scripts.
Generated dependencies/build outputs and local virtual environments are
present but are not application source.

## 2. Feature inventory

For this table, **Full** means a usable UI/API/data workflow is present; it
does **not** mean production readiness. **Partial** means code exists but a
notable path, type, management action, or operational guarantee is absent or
restricted. Front/API/DB: **Y** = implemented, **P** = partial, **N** = absent
or not applicable. This is a count of feature areas, not individual buttons or
API routes.

| # | Feature area | Front | API | DB | Readiness | Main implementation |
|---:|---|:---:|:---:|:---:|---|---|
| 1 | Register, log in, log out | Y | Y | Y | Partial: no password reset, MFA, or email verification found | [`frontend/app/page.tsx`](../frontend/app/page.tsx), [`backend/app/main.py`](../backend/app/main.py), [`backend/app/security.py`](../backend/app/security.py) |
| 2 | Current-user/session validation and revocation | Y | Y | Y | Partial: no separate refresh-token flow found | [`frontend/app/auth-routing.ts`](../frontend/app/auth-routing.ts), [`backend/app/security.py`](../backend/app/security.py), [`backend/app/models.py`](../backend/app/models.py) |
| 3 | Super-admin user/participant directory | Y | Y | Y | Partial: visible records are primarily display/search; limited mutation controls | [`frontend/app/admin/page.tsx`](../frontend/app/admin/page.tsx), [`backend/app/admin_routes.py`](../backend/app/admin_routes.py) |
| 4 | Organization workspace and switching | Y | Y | Y | Partial: member-management actions are limited | [`frontend/app/page.tsx`](../frontend/app/page.tsx), [`backend/app/main.py`](../backend/app/main.py) |
| 5 | Organization settings and audit API | N | Y | Y | Backend-only surface; frontend settings/audit workflow not established | [`backend/app/organization_routes.py`](../backend/app/organization_routes.py), [`backend/app/models.py`](../backend/app/models.py) |
| 6 | Membership roles and permission checks | Y | Y | Y | Partial: role model exists, but no invitation/member-creation flow was found | [`backend/app/permissions.py`](../backend/app/permissions.py), [`backend/app/organization_routes.py`](../backend/app/organization_routes.py) |
| 7 | Department listing, creation, assignment/scoping | Y | Y | Y | Partial: management surface is narrower than full department administration | [`frontend/app/page.tsx`](../frontend/app/page.tsx), [`backend/app/organization_routes.py`](../backend/app/organization_routes.py) |
| 8 | Presentation create/list/rename | Y | Y | Y | Partial: no complete lifecycle/status management UI established | [`frontend/app/page.tsx`](../frontend/app/page.tsx), [`backend/app/main.py`](../backend/app/main.py), [`backend/app/models.py`](../backend/app/models.py) |
| 9 | Presentation question editor | Y | Y | Y | Partial: supported behavior depends on question kind; revisions guard saves | [`frontend/app/editor/[org]/[id]/page.tsx`](../frontend/app/editor/%5Borg%5D/%5Bid%5D/page.tsx), [`backend/app/builder_routes.py`](../backend/app/builder_routes.py) |
| 10 | Scheduled/assigned quizzes | Y | Y | Y | Full workflow exists; supported assigned-quiz kinds are limited | [`frontend/app/schedule-panel.tsx`](../frontend/app/schedule-panel.tsx), [`backend/app/scheduled_routes.py`](../backend/app/scheduled_routes.py) |
| 11 | Student profile, history, and achievements | Y | Y | Y | Full display and threshold-setting flow; production operation not certified | [`frontend/app/student-dashboard.tsx`](../frontend/app/student-dashboard.tsx), [`backend/app/student_routes.py`](../backend/app/student_routes.py) |
| 12 | Question bank search, view, add, reuse | Y | Y | Y | Partial: bank listing does not provide full edit/delete management UI | [`frontend/app/bank/[org]/page.tsx`](../frontend/app/bank/%5Borg%5D/page.tsx), [`frontend/app/question-bank-picker.tsx`](../frontend/app/question-bank-picker.tsx), [`backend/app/builder_routes.py`](../backend/app/builder_routes.py) |
| 13 | Shared question validation and scoring model | Y | Y | Y | Partial: not all kinds are live-scored | [`backend/app/questions.py`](../backend/app/questions.py), [`backend/app/models.py`](../backend/app/models.py) |
| 14 | Live host controls | Y | Y | Y | Partial: manual next-question advancement is not implemented | [`frontend/app/live/[id]/page.tsx`](../frontend/app/live/%5Bid%5D/page.tsx), [`backend/app/live_routes.py`](../backend/app/live_routes.py) |
| 15 | Join by live quiz code and submit participant registration | Y | Y | Y | Full join workflow; requires valid session/code and participant credentials | [`frontend/app/join/page.tsx`](../frontend/app/join/page.tsx), [`backend/app/live_routes.py`](../backend/app/live_routes.py) |
| 16 | Participant credential recovery/rejoin | Y | Y | Y | Full server-side token/answer persistence; browser-side recovery is partial | [`frontend/app/participant-storage.ts`](../frontend/app/participant-storage.ts), [`backend/app/live_routes.py`](../backend/app/live_routes.py) |
| 17 | Live answer submission, timer, scoring | Y | Y | Y | Partial: several accepted answer kinds are ungraded; timer behavior is server-constrained | [`frontend/app/join/page.tsx`](../frontend/app/join/page.tsx), [`backend/app/questions.py`](../backend/app/questions.py), [`backend/app/live_routes.py`](../backend/app/live_routes.py) |
| 18 | Host results, response snapshots, leaderboard | Y | Y | Y | Full for implemented session reporting; no host-side question advance | [`frontend/app/live/[id]/page.tsx`](../frontend/app/live/%5Bid%5D/page.tsx), [`backend/app/live_routes.py`](../backend/app/live_routes.py) |
| 19 | Live WebSocket delivery | Y | Y | N (Redis pub/sub) | Partial: reconnect/polling helps recovery; production scale not load-tested | [`frontend/app/use-live-socket.ts`](../frontend/app/use-live-socket.ts), [`backend/app/live_routes.py`](../backend/app/live_routes.py) |
| 20 | Session/question/participant analytics | Y | Y | Y | Full for reported live-session analytics; not a broad institutional analytics suite | [`frontend/app/analytics/[org]/page.tsx`](../frontend/app/analytics/%5Borg%5D/page.tsx), [`backend/app/analytics_routes.py`](../backend/app/analytics_routes.py) |
| 21 | CSV, XLSX, PDF, PNG report exports | Y | Y | Y | Export paths exist; production output quality was not separately validated | [`frontend/app/analytics/[org]/page.tsx`](../frontend/app/analytics/%5Borg%5D/page.tsx), [`backend/app/analytics_routes.py`](../backend/app/analytics_routes.py) |
| 22 | AI question generation and review | Y | Y | P | Full UI/API generation flow; successful provider operation/output quality not guaranteed by source inspection | [`frontend/app/ai-question-generator.tsx`](../frontend/app/ai-question-generator.tsx), [`backend/app/ai_routes.py`](../backend/app/ai_routes.py) |
| 23 | Document question extraction | Y | Y | Y | Partial: supported formats and visual extraction have limits | [`frontend/app/question-importer.tsx`](../frontend/app/question-importer.tsx), [`backend/app/document_structure.py`](../backend/app/document_structure.py), [`backend/app/import_pipeline.py`](../backend/app/import_pipeline.py) |
| 24 | Import preview, faculty review, commit | Y | Y | Y | Full preview/review/commit flow; approval and unresolved-error handling are required | [`frontend/app/question-importer.tsx`](../frontend/app/question-importer.tsx), [`backend/app/import_routes.py`](../backend/app/import_routes.py), [`backend/app/models.py`](../backend/app/models.py) |
| 25 | AI-assisted import interpretation/answer suggestion | Y | Y | P | Partial: optional provider/render services and faculty review; suggestions are unverified | [`backend/app/document_ai.py`](../backend/app/document_ai.py), [`backend/app/import_routes.py`](../backend/app/import_routes.py) |
| 26 | Browser refresh/network recovery for live students | Y | P | P | Partial: token persistence and refresh/reconnect paths exist, but depend on retained browser storage and service availability | [`frontend/app/join/page.tsx`](../frontend/app/join/page.tsx), [`frontend/app/participant-storage.ts`](../frontend/app/participant-storage.ts) |
| 27 | Redis rate limits, pub/sub, one-use WebSocket tickets | N | Y | Y (Redis) | Backend-only infrastructure behavior; not a user-facing UI feature | [`backend/app/security.py`](../backend/app/security.py), [`backend/app/live_routes.py`](../backend/app/live_routes.py), [`backend/app/ai_routes.py`](../backend/app/ai_routes.py) |
| 28 | Health checks and generated API docs | N | Y | N | Backend-only; interactive docs are configured by FastAPI | [`backend/app/main.py`](../backend/app/main.py) |
| 29 | Business Celery/background jobs | N | P | N | Placeholder for business work: worker currently registers a health task, not quiz business jobs | [`backend/app/worker.py`](../backend/app/worker.py), [`backend/app/main.py`](../backend/app/main.py) |
| 30 | Responsive and accessibility-oriented UI behavior | Y | N | N | Partial: labels, status roles, focus styling, mobile/reduced-motion styles exist; full accessibility conformance not tested | [`frontend/app/globals.css`](../frontend/app/globals.css), [`frontend/app/student-quiz.css`](../frontend/app/student-quiz.css), [`frontend/app/join/page.tsx`](../frontend/app/join/page.tsx) |

### Feature counts

**Total features found: 30** (using the feature-area grouping above)

- Fully implemented workflows: **9**
- Partially implemented: **17**
- Backend only: **3**
- Frontend only: **0**
- Planned/placeholder only: **1**

These categories are mutually exclusive for the counts. “Full” means the
primary workflow is wired across its relevant surfaces; it does not certify
production readiness.

## 3. User roles and access

There are **five membership roles** constrained in the database, plus a
separate super-admin flag. Thus, there are **6 authorization roles/tiers**.
`teacher` and `student` are `User.profession` values, not membership roles.

| Role/tier | Permissions and access evidenced in code |
|---|---|
| **Super Admin** | Separate `is_super_admin` user flag; accesses super-admin summary/user/participant APIs and `/admin`. It is not a membership role. See [`models.py`](../backend/app/models.py), [`admin_routes.py`](../backend/app/admin_routes.py), [`admin/page.tsx`](../frontend/app/admin/page.tsx). |
| **Owner** | Organization-wide permissions including organization/member/department/audit and billing capability in the permission policy; owns the organization created at teacher registration. See [`permissions.py`](../backend/app/permissions.py), [`main.py`](../backend/app/main.py). |
| **Admin** | Broad organization management, similar to owner but without owner-only billing capability in the permission set. See [`permissions.py`](../backend/app/permissions.py). |
| **Department Admin** | Department-scoped administration/member management; scope checks require organization and department relationship. See [`permissions.py`](../backend/app/permissions.py), [`organization_routes.py`](../backend/app/organization_routes.py). |
| **Faculty** | Presentation read/write, session control, analytics read, and bank write subject to organization/resource scope. See [`permissions.py`](../backend/app/permissions.py). |
| **Faculty Lite** | No broad role grants by default; an organization-configured subset of faculty permissions applies. See [`models.py`](../backend/app/models.py), [`permissions.py`](../backend/app/permissions.py). |
| **Student** | Student is a profession, not membership role. Students use student profile/assigned quiz routes and may join a live session as a participant. See [`models.py`](../backend/app/models.py), [`student_routes.py`](../backend/app/student_routes.py), [`live_routes.py`](../backend/app/live_routes.py). |

**Not found as defined roles:** Co-Presenter is not in the membership role
constraint; “teacher” is a profession/account type, not a membership role.
Students use a separate experience. Most faculty/organization users share the
root workspace with role-conditioned UI; students and super-admins have
separate `/student` and `/admin` routes. There is no separate dashboard per
membership role.

## 4. Frontend routes

**Total frontend pages/routes: 9**

| Route | Purpose / access | Main file |
|---|---|---|
| `/` | Sign-in/register; teacher workspace or student dashboard depending on current user | [`frontend/app/page.tsx`](../frontend/app/page.tsx) |
| `/admin` | Super-admin directory/summary and settings | [`frontend/app/admin/page.tsx`](../frontend/app/admin/page.tsx) |
| `/student` | Student profile/dashboard | [`frontend/app/student/page.tsx`](../frontend/app/student/page.tsx) |
| `/join` | Join/rejoin a live quiz and answer | [`frontend/app/join/page.tsx`](../frontend/app/join/page.tsx) |
| `/quiz/[id]` | Assigned student quiz | [`frontend/app/quiz/[id]/page.tsx`](../frontend/app/quiz/%5Bid%5D/page.tsx) |
| `/editor/[org]/[id]` | Presentation/question editor and scheduling | [`frontend/app/editor/[org]/[id]/page.tsx`](../frontend/app/editor/%5Borg%5D/%5Bid%5D/page.tsx) |
| `/live/[id]` | Host live-session view | [`frontend/app/live/[id]/page.tsx`](../frontend/app/live/%5Bid%5D/page.tsx) |
| `/bank/[org]` | Organization question bank | [`frontend/app/bank/[org]/page.tsx`](../frontend/app/bank/%5Borg%5D/page.tsx) |
| `/analytics/[org]` | Session selection, analytics, and downloads | [`frontend/app/analytics/[org]/page.tsx`](../frontend/app/analytics/%5Borg%5D/page.tsx) |

## 5. Backend API endpoints

The count is based on route declarations in the current FastAPI app:
**59 route handlers: 58 HTTP routes plus 1 WebSocket route.** The 58 HTTP
routes include two health endpoints. Authentication and permissions vary within
each endpoint family.

| Methods and endpoints | Purpose/access summary | Source |
|---|---|---|
| `GET /health/live`; `GET /health/ready` | Liveness/readiness; unauthenticated health checks | [`main.py`](../backend/app/main.py) |
| `POST /api/v1/auth/register`; `POST /api/v1/auth/login`; `POST /api/v1/auth/logout`; `GET /api/v1/auth/me` | Account/session operations; registration/login are public with origin/rate controls; logout/current-user require session context | [`main.py`](../backend/app/main.py) |
| `GET /api/v1/organizations`; `GET /api/v1/organizations/{org_id}/members`; `GET /api/v1/organizations/{org_id}/departments`; `POST /api/v1/organizations/{org_id}/departments` | Organization and department listing/create; authenticated and organization permission-scoped | [`main.py`](../backend/app/main.py) |
| `GET /api/v1/organizations/{org_id}/presentations`; `POST /api/v1/organizations/{org_id}/presentations`; `PATCH /api/v1/organizations/{org_id}/presentations/{presentation_id}` | Presentation list/create/rename; organization permission-scoped | [`main.py`](../backend/app/main.py) |
| `GET /api/v1/organizations/{org_id}/settings`; `PATCH /api/v1/organizations/{org_id}/settings`; `PATCH /api/v1/organizations/{org_id}/members/{membership_id}`; `GET /api/v1/organizations/{org_id}/departments/{department_id}/members`; `GET /api/v1/organizations/{org_id}/audit` | Organization settings, role change, department membership, audit; authenticated with role/scope checks | [`organization_routes.py`](../backend/app/organization_routes.py) |
| `GET /api/v1/organizations/{org_id}/presentations/{presentation_id}/slides`; `PUT /api/v1/organizations/{org_id}/presentations/{presentation_id}/slides`; `GET /api/v1/organizations/{org_id}/bank/questions`; `POST /api/v1/organizations/{org_id}/bank/questions`; `POST /api/v1/organizations/{org_id}/bank/questions/bulk` | Presentation questions and question bank; authenticated, permission-scoped; writes enforce origin checks | [`builder_routes.py`](../backend/app/builder_routes.py) |
| `POST /api/v1/organizations/{org_id}/presentations/{presentation_id}/sessions`; `POST /api/v1/sessions/join`; `POST /api/v1/sessions/{session_id}/control`; `GET /api/v1/sessions/{session_id}/host`; `GET /api/v1/sessions/{session_id}/participant`; `POST /api/v1/sessions/{session_id}/responses`; `GET /api/v1/sessions/{session_id}/results`; `POST /api/v1/sessions/{session_id}/host-ticket`; `POST /api/v1/sessions/{session_id}/participant-ticket`; `WS /api/v1/live/ws` | Live-session creation, join, control, snapshots/results, answer submit, WebSocket tickets/feed. Host operations require faculty permissions; participant calls use session/participant credentials; WebSocket requires ticket/origin checks | [`live_routes.py`](../backend/app/live_routes.py) |
| `GET /api/v1/organizations/{org_id}/sessions`; `GET /api/v1/sessions/{session_id}/analytics`; `GET /api/v1/sessions/{session_id}/export/{format}` | Session list, analytics, CSV/XLSX/PDF/PNG export; authenticated and permission-scoped | [`analytics_routes.py`](../backend/app/analytics_routes.py) |
| `POST /api/v1/organizations/{org_id}/imports/preview`; `POST /api/v1/organizations/{org_id}/imports/preview/file`; `POST /api/v1/organizations/{org_id}/imports/{batch_id}/review`; `POST /api/v1/organizations/{org_id}/imports/{batch_id}/questions/{question_index}/suggest-answer`; `POST /api/v1/organizations/{org_id}/imports/{batch_id}/commit`; `POST /api/v1/organizations/{org_id}/imports/{batch_id}/presentation/{presentation_id}` | Import preview, review, optional answer suggestion, commit to bank or presentation; owner-scoped batch plus authorization/review checks | [`import_routes.py`](../backend/app/import_routes.py) |
| `POST /api/v1/organizations/{org_id}/ai/generate-questions`; `POST /api/v1/organizations/{org_id}/ai/generate-questions/document`; `POST /api/v1/organizations/{org_id}/ai/generate-questions/image` | Generate from text/topic, documents, or images; authenticated, organization permission and AI-limit checks | [`ai_routes.py`](../backend/app/ai_routes.py) |
| `POST /api/v1/organizations/{org_id}/presentations/{presentation_id}/schedule`; `GET /api/v1/student/quizzes`; `GET /api/v1/student/quizzes/{quiz_id}`; `GET /api/v1/student/quizzes/{quiz_id}/results`; `POST /api/v1/student/quizzes/{quiz_id}/submit`; `POST /api/v1/student/quizzes/{quiz_id}/start`; `PUT /api/v1/student/quizzes/{quiz_id}/draft`; `GET /api/v1/organizations/{org_id}/presentations/{presentation_id}/schedules` | Create/list schedules; student assigned-quiz list/start/draft/submit/results; student/teacher identity and access checks | [`scheduled_routes.py`](../backend/app/scheduled_routes.py) |
| `GET /api/v1/admin/summary`; `GET /api/v1/admin/users`; `GET /api/v1/admin/participants` | Super-admin aggregates and searchable/paginated directories; super-admin-only | [`admin_routes.py`](../backend/app/admin_routes.py) |
| `GET /api/v1/admin/achievement-settings`; `PUT /api/v1/admin/achievement-settings`; `GET /api/v1/student/profile` | Achievement configuration and student profile; admin/student scope checks | [`student_routes.py`](../backend/app/student_routes.py) |

## 6. Database structure

**Total database tables/models: 18.** Model declarations are in
[`backend/app/models.py`](../backend/app/models.py); migrations are in
[`backend/migrations/versions/`](../backend/migrations/versions/). The schema
uses UUID identities, foreign keys, JSON fields, uniqueness/check constraints,
and indexes. The checked-in
[`docs/postgresql-schema.sql`](./postgresql-schema.sql) is behind the current
migration chain.

| Table/model | Purpose and notable fields/relationships |
|---|---|
| `users` | Profession, unique email, name, password hash, active and `is_super_admin`; profession constrained to teacher/student. |
| `organizations` | Name and configurable faculty-lite permissions. |
| `memberships` | User ↔ organization; unique per organization/user; constrained role. |
| `departments` | Organization-owned department; unique name per organization. |
| `department_assignments` | Composite organization/membership/department mapping; composite foreign keys protect tenant consistency. |
| `auth_sessions` | User session expiry and revocation state. |
| `audit_events` | Actor, optional organization, action and resource identifier. |
| `presentations` | Organization, owner, optional department, title, revision, status and duration. |
| `slides` | Presentation, ordinal, JSON question; unique ordinal per presentation. |
| `bank_questions` | Organization/owner, subject/chapter/topic/difficulty/tags and JSON question. |
| `live_sessions` | Presentation/org/owner, unique join code, state, active index, revision, question snapshot, opened time. |
| `participants` | Session, optional profile, nickname, unique hashed credential; unique participant profile per session. |
| `participant_profiles` | Participant identity fields such as name, unique email and phone. |
| `answers` | Session, participant, question index, JSON answer, correctness, score and elapsed time; unique session/participant/question. |
| `achievement_settings` | Singleton thresholds for gold/platinum/diamond, with ordering checks. |
| `import_batches` | Owner-scoped persisted import preview/review state with expiry. |
| `scheduled_quizzes` | Scheduled quiz/presentation snapshot and time window. |
| `quiz_assignments` | Student email/assignment/attempt state, drafts and results for scheduled quizzes. |

## 7. Question types

The canonical model defines **15 types** in
[`backend/app/questions.py`](../backend/app/questions.py). The editor, bank,
and import pipeline can represent more types than the live-session scorer can
grade. Several accepted live answer kinds are explicitly ungraded.

| Type | Author/bank/import | Live response | Scoring |
|---|---|---|---|
| MCQ (`mcq`) | Yes | Yes | Correct/incorrect, marks, negative marks, speed bonus |
| Multiple select | Yes | Yes | Exact set comparison |
| True/False | Yes | Yes | Correct/incorrect |
| Quiz (`quiz`) | Yes | Yes | Single correct option |
| Poll | Yes | Yes | Response accepted; ungraded |
| Short answer | Yes | Yes | Optional exact accepted-answer match; otherwise ungraded |
| Ranking | Yes | Yes | Ranking accepted; ungraded |
| Scale | Yes | Yes | Range-validated; ungraded |
| Rating | Yes | Yes | Range-validated; ungraded |
| NPS | Yes | Yes | 0–10 validated; ungraded |
| Word cloud | Yes | Yes | Text accepted; ungraded |
| Q&A (`qa`) | Yes | Yes | Text accepted; ungraded |
| Survey | Yes | Yes | Text accepted; ungraded |
| Form | Yes | No live answer evaluator established | Not scored live |
| Content | Yes | No live answer evaluator established | Not scored live |

**Total question types: 15.** “Yes” in author/bank/import means the shared
model/import schema can represent the type; it does not mean every type is
supported by every live/scheduled flow. Scheduled assignments support a
narrower set.

## 8. Live quiz, rejoin, analytics, and Redis

- **Starting a session:** a presentation's questions are snapshotted into a
  persisted live session, which receives a unique six-digit join code. Host
  actions open, close answers, or end the session. The code does not expose a
  host credential.
- **Joining:** students submit the quiz code/session identifier and participant
  details when requested. Repeat join requires the participant's existing
  token; matching only an email/contact value does not reveal it.
- **Participant persistence:** a random participant credential is issued to
  the browser; the server stores its hash. Answers are persisted and unique
  per participant/question.
- **Question progression:** participants advance from their own next
  unanswered question. The host-side `active_index` does not have an
  implemented advancement path in the inspected code, and manual `next` is
  disabled/conflicts. Live creation also excludes some slide kinds.
- **Answers/timers/scoring:** responses must arrive while the session is open
  and before the question timer expires. Score stores thousandths of a mark;
  correctness, negative marks, and speed bonus are supported for applicable
  types.
- **Leaderboard:** derived from durable answers and ordered by score, correct
  count, elapsed time, and participant identifier.
- **WebSockets:** host/participant ticket endpoints issue short-lived,
  one-use Redis tickets. The socket checks origin and ticket, subscribes to
  Redis pub/sub, sends heartbeats, and closes idle connections. Frontend
  reconnect and snapshot polling provide recovery paths.
- **Rejoin/resume:** browser refresh and network recovery are **partially
  implemented**: participant tokens are saved/looked up in browser storage;
  API state and answers persist; WebSocket reconnect and refresh events exist.
  Timer state is server-time based. This is not a universal recovery guarantee:
  cleared storage or another browser/device may prevent reuse of the
  participant token.
- **Duplicate attempts:** database uniqueness prevents duplicate answer
  records for the same session/participant/question. Participant/session
  profile uniqueness also limits duplicate participant records for the same
  profile.
- **Multiple backend workers:** Redis pub/sub and database persistence allow
  cross-process live notifications/state reads in design. However, no
  load/multi-node verification was performed. Scheduled expiry is a loop in
  each API process, not a distributed Celery job; multi-replica concurrency
  behavior is therefore not established.
- **Analytics:** session/question response rate and accuracy, participant
  performance, hardest/easiest questions, and live leaderboard. No broad
  faculty/organization analytics suite beyond session reports and super-admin
  summary counts was established.
- **Redis uses:** login/register and AI/live rate limits; live pub/sub;
  WebSocket one-use tickets; readiness check; Celery broker/result backend.
  No general-purpose cache, WebSocket presence store, or authoritative
  live-session database was established from code.

## 9. Question bank

Implemented: create one or bulk questions, list/search bank questions, store
subject/chapter/topic/difficulty/tags, select bank questions into an editor
presentation, and save authored questions to the bank. Backend access is
permission/owner scoped.

**Not established:** full bank edit/delete controls, robust category taxonomy,
bulk delete/edit, or an export operation dedicated to bank records. General
analytics exports exist separately. See
[`builder_routes.py`](../backend/app/builder_routes.py),
[`bank/[org]/page.tsx`](../frontend/app/bank/%5Borg%5D/page.tsx), and
[`question-bank-picker.tsx`](../frontend/app/question-bank-picker.tsx).

## 10. File import

Supported upload formats per the current importer: **PDF, DOCX, PPTX, XLSX,
CSV, TXT, JSON**. Standalone legacy DOC/PPT/XLS need optional configured
conversion; otherwise an export-to-supported-format error is expected.
Standalone images are not listed as question-document upload formats, but
embedded images can be extracted and passed into document interpretation.

| Format | Status |
|---|---|
| PPTX | **SUPPORTED**; slide text/tables/notes/structure and embedded images are extracted. |
| PPT | **PARTIALLY SUPPORTED**; only if optional conversion service is configured; otherwise unsupported. |
| PDF | **SUPPORTED**; text and embedded images; image-only pages require OCR/rendering/vision. |
| DOCX | **SUPPORTED**; paragraphs/tables and embedded images; document is treated as a single render section. |
| DOC | **PARTIALLY SUPPORTED**; optional conversion only. |
| XLSX | **SUPPORTED**; spreadsheet rows/sheets supported. |
| CSV | **SUPPORTED** |
| TXT | **SUPPORTED** |
| JSON | **SUPPORTED**; schema validated per row. |
| Standalone image upload | **NOT SUPPORTED by question-import file formats**; the separate AI generator accepts image input. |

The code uses python-pptx/PDF, ZIP/XML extraction, and spreadsheet/document
parsers in [`document_structure.py`](../backend/app/document_structure.py),
[`document_import.py`](../backend/app/document_import.py), and
[`import_parser.py`](../backend/app/import_parser.py). The import flow includes
preview, validation, editable review, and commit. It preserves source evidence,
reads PPTX speaker notes and tables, and rejects malformed/unsupported fields
rather than silently accepting them. Embedded images are bounded and can be
sent to Gemini interpretation; correct answers are extracted only from
explicit evidence, not inferred from subject knowledge. Optional rendering and
conversion services are deployment configuration, not bundled services. See
[`QUESTION_DOCUMENT_IMPORT.md`](./QUESTION_DOCUMENT_IMPORT.md).

## 11. AI integration

- **Question generation providers:** OpenAI and Gemini, selected/configured
  by `AI_PROVIDER`; settings include `GEMINI_API_KEY`,
  `GEMINI_QUESTION_MODEL`, `OPENAI_API_KEY`, and `OPENAI_QUESTION_MODEL`.
  Defaults are in [`config.py`](../backend/app/config.py) and
  [`.env.example`](../.env.example).
- **APIs:** [`ai_routes.py`](../backend/app/ai_routes.py) and provider/prompt
  logic in [`ai_question_generator.py`](../backend/app/ai_question_generator.py).
- **Inputs:** topic/text, PDF/PPTX/TXT document, JPG/PNG/WEBP image.
  Generation output is constrained to a subset of question types, then
  validated.
- **Frontend:** [`ai-question-generator.tsx`](../frontend/app/ai-question-generator.tsx)
  supports options such as type/count, difficulty, and language; generated
  drafts can be edited, selected, regenerated, added to a presentation, or
  saved to the bank.
- **Import AI:** [`document_ai.py`](../backend/app/document_ai.py) provides
  document interpretation and optional answer suggestion with review
  requirements. AI answer suggestions are explicitly unverified.
- **Limitations:** provider keys/service availability and output quality
  cannot be concluded from code alone. Rendering and legacy conversion are
  optional services, not enabled by mere source presence. AI is implemented,
  not just planned.

## 12. Security and production limitations

| Control | What exists | Caveat |
|---|---|---|
| Password hashing | `pwdlib` password hashing | No password-reset or MFA flow found. |
| Auth | JWT in HttpOnly cookie plus persisted, revocable auth session | No separate refresh-token endpoint found. |
| Cookie flags | SameSite=Strict; Secure in production | Deployment configuration still matters. |
| Authorization | Role/permission policy and organization/department resource scope | No broad independent penetration verification performed. |
| CSRF/origin | Origin checks on mutation paths plus SameSite cookie | Not a separate CSRF-token system. |
| Rate limiting | Redis-backed atomic limits; auth limiter fails closed if Redis unavailable | Limits and production behavior need deployment/load testing. |
| Upload validation | File size limits, extension/signature checks, ZIP/archive bounds, content-specific validation | No malware scanning or operational upload stress test established. |
| SQL injection | SQLAlchemy query patterns in inspected application code | This is a source observation, not a security certification. |
| XSS | React rendering normally escapes text | No project-wide security scan or explicit rich-HTML sanitization audit was run. |
| WebSocket auth | Short-lived one-use ticket, origin check, participant/host authorization | Depends on secret and Redis availability; no multi-node load test. |
| Secrets | Environment-based settings and production configuration checks | Compose is explicitly a local baseline; managed secrets/TLS are deployment responsibilities. |
| CORS/production mode | Configuration is present | Full deployment-policy validation was not performed; see [`config.py`](../backend/app/config.py) and [`compose.yaml`](../compose.yaml). |

**Important weaknesses before production:** missing account recovery/MFA/email
verification; limited operational assurance for uploads and provider services;
local Compose does not provide production TLS/managed secrets/backups; no load,
penetration, real multi-node, or production PostgreSQL/Redis verification was
performed in this audit.

## 13. Docker, API docs, and background jobs

Compose services: `postgres`, `redis`, `migrate`, `api`, `worker`, and `web`.
PostgreSQL and Redis have health checks/persistent volumes; API has a readiness
health check. API/web ports bind to loopback. The Compose file calls out
production TLS, managed secrets, and backups as required.

FastAPI generates OpenAPI and exposes interactive docs at `/docs`; no
checked-in standalone OpenAPI specification or CI workflow was found. The
Celery task is health-only; scheduled quiz expiry is performed by an
in-process API loop. No business email, document, analytics, or cleanup Celery
task was established.

## 14. Tests

**Total test files: 25** (20 backend Python modules and 5 frontend `.test.mjs`
modules). Backend tests cover auth, permissions, rate limits, organizations,
live quiz, imports, AI, scheduling/timers, results, and student profiles.
Frontend tests cover API errors, auth routing, live state merging, participant
storage, and question-edit normalization. See
[`backend/tests/`](../backend/tests) and
[`frontend/tests/`](../frontend/tests).

The infrastructure audit counted **204 backend tests collected** and **154
explicit `test_` function declarations** (parameterization makes those counts
differ); the frontend has **19 test declarations** across its five files.
These are static/collection counts, not a test run for this audit. Frontend
package scripts include build/typecheck but no frontend test command. Main
gaps: no route/component test suite was found, and fixtures replace some real
DB/Redis behavior, so passing unit tests alone would not establish production
readiness.

## 15. TODOs, placeholders, and dead-code caveats

Confirmed incompleteness from source: Celery has only a health task; host-side
manual `next` is disabled/conflicts; import conversion/rendering services are
optional external services; full question-bank edit/delete UI was not found.
The current SQL schema snapshot is older than the Alembic head. These are
concrete limitations, not evidence that the rest of the features are unused.

I cannot reliably classify all modules as used/unused from source inspection
alone. No claim of dead code is made without call-site/build evidence. The
audit did not identify inert UI buttons exhaustively; no route/component test
suite was found to prove button behavior throughout the application.

## 16. Scorecard and executive summary

Percentages below are rough implementation-coverage estimates, **not measured
quality or production-readiness scores**.

| Area | Status | Estimate |
|---|---|---:|
| Authentication | Implemented baseline; recovery features absent | 70% |
| Organization/department management | Role-scoped core, limited member lifecycle UI | 65% |
| Roles and authorization | Persisted permission model and scoping | 75% |
| Question bank | Create/list/search/reuse; limited full management | 65% |
| Live quiz | Durable join/answer/results; host progression incomplete | 65% |
| Student experience | Join, assigned quizzes, dashboard and recovery paths | 75% |
| Analytics and export | Session-level reports and four formats | 75% |
| AI | Provider-backed generation and import assistance | 70% |
| Import system | Seven document formats and review workflow; rendering/conversion conditional | 75% |
| Realtime/WebSockets | Ticketed sockets, Redis pub/sub and reconnect snapshots | 70% |
| Security | Good baseline controls; production assurance incomplete | 60% |
| Testing | Broad backend coverage, helper-level frontend tests | 60% |
| Production deployment | Local Compose baseline only | 35% |

### Executive summary

1. **What Quizeee can do today:** create accounts and organizations, author
   presentations/questions, schedule certain quizzes, manage a question bank,
   run live quizzes with code-based student join, persist answers/results,
   show leaderboards and session analytics, export reports, generate AI
   question drafts, and preview/review/import documents.
2. **What it can partially do:** full organization/member administration,
   question-bank lifecycle, live host question progression, live
   support/scoring across every question type, cross-device participant
   recovery, document visual interpretation without optional services, broad
   institutional analytics, and production deployment.
3. **Planned/placeholder or absent:** business Celery jobs, password
   reset/MFA/email verification, and a fully implemented host `next` action
   are not present in the inspected code. Optional document
   conversion/rendering depends on external service configuration.
4. **Biggest technical strengths:** persisted domain model, tenant/department
   permission checks, unique constraints for duplicate answers, explicit
   answer validation, preview/review import safeguards, and Redis-backed live
   notifications/rate limits.
5. **Biggest technical weaknesses:** host progression is incomplete; Celery
   has no business work; the local Compose setup is not production
   infrastructure; frontend tests are helper-focused; the current SQL
   snapshot is stale; production/load/penetration/multi-node behavior is
   unverified.
6. **Before production:** establish account recovery and operational security
   practices, verify production secret/TLS/backup configuration, test real
   PostgreSQL/Redis and provider failure paths, and reconcile docs/schema
   snapshots.
7. **Before 500+ participants:** benchmark DB writes and WebSocket fan-out,
   verify multi-worker pub/sub/reconnect behavior, size/tune Redis and
   connection pools, and ensure timer/expiry work is safe across multiple API
   instances.
8. **Recommended next 10 tasks, in priority order:**
   1. Implement or clarify host question progression.
   2. Run multi-worker live-session load tests.
   3. Make expiry processing safe across replicas.
   4. Establish production deployment, TLS, secret, and backup configuration.
   5. Add password reset/email verification and account recovery.
   6. Test WebSocket/rejoin scenarios end to end.
   7. Expand frontend route/component tests.
   8. Add full bank edit/delete/bulk management.
   9. Complete assignment/live support for intended question types.
   10. Update the schema snapshot and deployment documentation.

### Requested totals

| Total | Count |
|---|---:|
| **TOTAL FEATURES** | **30** grouped feature areas |
| **TOTAL FRONTEND ROUTES** | **9** |
| **TOTAL API ENDPOINTS** | **59** route handlers: 58 HTTP + 1 WebSocket |
| **TOTAL DATABASE MODELS** | **18** |
| **TOTAL USER ROLES** | **6 authorization tiers**: 5 membership roles + separate Super Admin flag |
| **TOTAL QUESTION TYPES** | **15** |
| **TOTAL TEST FILES** | **25**: 20 backend + 5 frontend |

**Counting note:** Student is a `profession` value rather than a membership
role, so it is not counted among the six authorization tiers. “Teacher” is
also a profession, not a membership role.
