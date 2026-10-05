# Quizeee

Original interactive teaching platform built with Next.js, React, TypeScript, Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Redis and Celery.

**Status: working development milestone, not a complete or production-ready SaaS release.** No production deployment or payment-provider connection has been made. The full requested scope is tracked below. The project was created in the available workspace because access to `D:\Quizeee` was not granted.

## Start here

- [System blueprint](docs/BLUEPRINT.md): architecture, PostgreSQL ERD, role-permission matrix, page inventory, API inventory, WebSocket protocol and ordered roadmap. Written before implementation.
- [Verification and release gaps](docs/VERIFICATION.md).
- [CSV question template](docs/question-import-template.csv).
- `backend/`: application, migrations and tests.
- `frontend/`: original Quizeee interface.
- `compose.yaml`: local PostgreSQL/Redis/API/worker/web setup.

## Delivered in this milestone

| Module | Working implementation | Still needed |
|---|---|---|
| Auth/RBAC | Argon2id passwords, JWT HttpOnly cookies, revocable sessions, origin checks, Redis rate limits, live membership lookup, tenant/department/owner policy checks, audit writes | Email verification/reset, rotating refresh tokens, MFA/reauthentication, OIDC, audited global admin workflows |
| Organization | Owner registration, organization list/switcher, member list; settings, Faculty Lite restrictions and role changes through APIs | Invitations, ownership transfer, license enforcement, member removal, richer administration UI |
| Departments | Create/list UI, assignments through membership API, scoped member query, department-admin role ceiling | Edit/archive UI and lifecycle constraints |
| Presentations | Create/list/search/rename, revision checks, original three-panel editor, add/duplicate/reorder/delete questions, manual save with unsaved-change warning | Autosave/revision merge, folders, templates, themes, notes, media, resource collaboration grants |
| Quiz builder | MCQ, multiple select, True/False, short answer, ranking, scales/ratings, Word Cloud text, polls, quiz, NPS and content; validated correct answers, marks, speed bonus and negative marking | Dedicated question-type visualizations; full forms, moderated Q&A and self-paced survey behavior |
| Question bank | Save and browse questions with metadata; CSV/XLSX validation preview and explicit idempotent commit | Bank-to-editor picker, edit/version history, shared department ownership, template/import creation chooser |
| Live | Unique join code, QR/link, anonymous nickname, waiting room/count, frozen question snapshot, open/close/next/end controls, server deadline and scoring, duplicate protection, leaderboard | Co-presenter grants, result-visibility controls, answer changes, separate winner screen, moderation, presence expiry, scalable response partitioning |
| Real time | Redis state cache and Pub/Sub invalidation; one-use 30-second WebSocket tickets; origin checks; 60-second socket lifetime and reauthorization; REST snapshot/poll recovery | Real Redis integration tests, durable event outbox and sequence/replay guarantees, multi-node/load verification |
| Analytics | Session history, counts/rates, accuracy, hardest/easiest, individual scores; CSV/XLSX/PDF/PNG exports | Organization-wide reports, worker-backed export jobs, international font coverage and pagination |
| Background work | Celery configured with JSON serialization, time limits and a health task | Import/export/AI/email queues, persisted jobs, retries, dead-letter handling |
| Billing / AI | Designed in blueprint | Not implemented; no payment or AI calls are simulated |
| Super Admin | Separate `/admin` dashboard for login accounts and live-quiz signups; paginated, searchable global directories with database-enforced authorization | Initial super-admin must be bootstrapped from the backend CLI; audited account management actions are not yet implemented |

The editor can store Q&A and survey question definitions, but starting a live session containing those types is explicitly rejected until their full workflows are implemented. Form definitions are also not live-enabled. Co-presenter is not present in organization roles. There is no public super-admin creation endpoint.

### Bootstrap the first super admin

To create a dedicated admin account directly, run this from the `backend` directory. Enter the password at the hidden terminal prompt; it is never included in the command line or output:

```powershell
.\venv\Scripts\python.exe -m app.bootstrap_super_admin create "Tuhina" admin@example.com
```

To promote an existing account instead, use:

```powershell
\.venv\Scripts\python.exe -m app.bootstrap_super_admin promote admin@example.com
```

For the Docker setup, use `docker compose exec api python -m app.bootstrap_super_admin create "Tuhina" admin@example.com`; the process prompts for the password in the terminal. The command refuses to run if a super admin already exists. Sign in with the new account; it opens `/admin`. The dashboard includes personal details from live-session signup records, so restrict access to trusted operators.

## Local setup with Docker

For the easiest Windows setup, follow [RUNNING.md](RUNNING.md) and run `Start-Quizeee.ps1` from the extracted project folder. The script creates unique local secrets automatically. It is also safe to start manually using the steps below.

Requires Docker Desktop with Compose. These services were **not** started in this environment because Docker/PostgreSQL/Redis executables were unavailable.

1. Copy `.env.example` to `.env`.
2. Set a unique hexadecimal `POSTGRES_PASSWORD` and a random `JWT_SECRET` of at least 32 characters. Hex avoids URL-escaping problems in the database URL. Do not use the example placeholder values.
3. Run from this project directory:

```powershell
docker compose up --build
```

4. Open `http://localhost:3000`. Create an organization to receive its owner role.
5. Create a presentation, open its title, add questions, save, then choose **Present**.
6. Open the join link in a separate browser/tab, enter a nickname, and open the question from the presenter tab.
7. Open **Analytics** from the workspace to inspect a session or download reports.

The migration service must finish before the API and worker start. Data persists in named PostgreSQL and Redis volumes. The website uses localhost port 3000 and the API uses localhost port 8010. If port 8010 is already occupied, change `API_PORT` and `NEXT_PUBLIC_WS_ORIGIN` together in `.env` before rebuilding. The web-to-API internal address remains `http://api:8000`.

QR links on localhost cannot be used from a phone. Phone testing needs a reachable test hostname, matching APP_ORIGIN/WS origin, deliberate network binding, and appropriate network access. Do not expose this development Compose configuration directly to the internet.

## Run without Docker

Provision PostgreSQL and Redis first. In `backend`, create a Python 3.12+ virtual environment, install `requirements.lock`, and set:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/quizeee
REDIS_URL=redis://HOST:6379/0
JWT_SECRET=<random secret>
APP_ORIGIN=http://localhost:3000
ENVIRONMENT=development
```

Then run:

```powershell
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In `frontend`, install Node.js 22+ and pnpm, run `pnpm install --frozen-lockfile`, then `pnpm dev`. Set `API_INTERNAL_URL` before starting Next.js if the API uses a different port. Set `NEXT_PUBLIC_WS_ORIGIN` before building for the public WebSocket origin. Run Celery in Linux or the supplied container; native Windows Celery workers are not the supported deployment path.

## Verification commands

```powershell
# From backend, with the virtual environment active
pytest -q -p no:cacheprovider
alembic upgrade head
alembic check

# From frontend
pnpm build
```

The test fixture uses SQLite with foreign-key enforcement and mocks Redis-dependent calls where stated. It does not prove PostgreSQL row-lock behavior or multi-worker Redis delivery. Production deployments must use PostgreSQL; SQLite is used only in tests and disposable UI verification.

## Production work still required

Complete the remaining feature modules, then run the gates in the blueprint. In particular: real PostgreSQL/Redis integration and race tests; database backup/restore; TLS and trusted proxy/rate-limit handling; email lifecycle; verified payment webhooks; AI provider/quota/approval workflows; private media storage; retention and deletion; bounded worker exports; migrations rehearsed on production-like data; monitoring; accessibility and browser coverage; and measured concurrency/load targets.

Current exports run synchronously and session responses lock a session row. These are appropriate initial implementations for validation, **not a claim of large-event production capacity**. Word Cloud responses currently render as text cards; a weighted cloud remains on the roadmap. A signed-in faculty member's bank is currently private unless they are owner/admin. Department-scoped bank administration is not yet wired.

No Mentimeter assets, trademarks, proprietary UI or source code are included. Quizeee is original project branding.
