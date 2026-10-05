# Run Quizeee on Windows

This package contains the current development implementation. It is not the complete production SaaS described in the original scope. Read README.md for the exact delivered and outstanding features.

## 1. Prepare Docker

Install Docker Desktop for Windows from https://www.docker.com/products/docker-desktop/ and start it. Use Linux containers. Follow Docker Desktop's setup instructions if Windows asks you to enable WSL 2 or restart. Wait until Docker reports that its engine is running.

Docker runs Python, Node.js, PostgreSQL, Redis and the background worker for you; you do not need to install those separately for this method. The first run needs internet access to download container images and packages.

## 2. Extract the project

Extract `Quizeee-project.zip` into `D:\`. The archive contains a top-level `Quizeee` folder, so the resulting file should be `D:\Quizeee\Start-Quizeee.ps1`. You can use another directory if preferred. Do not overwrite another existing project without checking it first.

## 3. Start

Open PowerShell in the Quizeee folder and run:

```powershell
cd D:\Quizeee
.\Start-Quizeee.ps1
```

The script checks Docker, creates `.env` with unique secrets only if it does not exist, builds the services, runs migrations, starts the containers, and waits for the website. It never replaces existing `.env` values or deletes database volumes.

If Windows blocks execution of the PowerShell script, use the manual steps below rather than changing your machine's execution policy.

## 4. Open and test

Open http://localhost:3000 in your browser.

1. Select **Create a workspace** and enter your name, organization, email and a password of at least 12 characters.
2. Create a presentation. Click its title to open the question editor.
3. Add questions, enter options and correct answers, then select **Save changes**.
4. Select **Present**. Share the displayed join link or code with a separate browser tab on the same computer.
5. Join as a participant using a nickname. In the presenter tab, select **Open question**.
6. Submit an answer from the participant tab. Check the response count and leaderboard on the presenter screen.
7. Close the question, move to the next question, or end the session.
8. Return to the workspace and open **Analytics** to view the session or download CSV, XLSX, PDF or PNG reports.

For question import, open **Question bank**, upload a CSV/XLSX file, review the preview and select **Confirm import**. The included `docs/question-import-template.csv` shows supported columns.

For AI question generation, set `AI_PROVIDER=gemini` and add your Gemini key to `.env` as `GEMINI_API_KEY=...`, then rebuild/restart with `docker compose up --build -d`. The key is passed only to the backend. Use **Generate with AI** in the Question Bank or presentation editor; generated questions remain drafts until selected and approved. Editor questions must still be saved before **Present**. See [AI question generation](docs/AI_QUESTION_GENERATOR.md) for limits and the API contract.

## Manual start, if script execution is blocked

From the Quizeee project directory:

```powershell
Copy-Item .env.example .env
notepad .env
```

Only copy the example if `.env` does not already exist. Replace both password placeholders with different random hexadecimal strings, each at least 64 characters long. Keep the other settings for the default local setup. Save and close the file, then run:

```powershell
docker compose up --build -d
docker compose ps
```

Wait for the containers to become ready, then open http://localhost:3000.

## Stop, restart and inspect

## Super-admin dashboard

Sign in with a super-admin account to open `/admin`. The dashboard shows teacher and student accounts, organizations, account status, registration/last-login dates, and live-quiz participant names, emails, phone numbers and scores. Search and pagination cover all records; use the account-type filter to view teachers or students separately. Phone numbers are collected during live joining, not account registration.

If no super admin has been configured, promote your existing account from the `backend` directory:

```powershell
.\venv\Scripts\python.exe -m app.bootstrap_super_admin promote your-email@example.com
```

Alternatively create the first admin with a hidden password prompt:

```powershell
.\venv\Scripts\python.exe -m app.bootstrap_super_admin create "Admin Name" your-email@example.com
```

These local commands refuse to bootstrap another super admin once one exists. Public registration cannot grant this role. Password hashes and session tokens are never included in dashboard responses.

## Service controls

## Student profiles and achievements

Open `http://localhost:3000/student`, or select **Go to Dashboard** after a live or assigned quiz. Registered students use their account email; a reusable participation profile is created automatically on their first attempt (or first profile visit). Existing quiz results are included automatically.

The dashboard shows the student's name and email, individual quiz history, marks, percentages, total points, completed and attempted quizzes, average/highest/lowest percentages, and achievement progress. Each completed quiz earns its percentage rounded to a whole number from 0 to 100; for example 80%, 70%, and 90% earn 240 total points. Negative results earn zero points. Ungraded quizzes earn zero points and are excluded from percentage averages. Live maximum marks include the available speed bonus. In-progress quizzes earn no points until completed or ended; scheduled timeouts use saved answers.

Totals are calculated from persisted quiz results, so reopening the dashboard or retrying a submission cannot award duplicate points. Badges use completed quiz counts: Gold at 10, Platinum at 50, and Diamond at 100 by default. A super admin can change these global thresholds in **Admin dashboard → Student achievements**. Changes apply to existing results without changing earned points.

New guest participants can access their profile in the browser where they first registered, using a private 30-day cookie. Entering an existing email on another browser does not grant access to its history. Sign in with a student account using the same email for access across browsers; once an account exists, its login is required.

For an existing local installation, apply the migration from `backend` with `.\venv\Scripts\python.exe -m alembic upgrade head` and restart the API. Docker startup applies migrations automatically.

## Service controls

```powershell
# Stop while retaining data
docker compose stop

# Start again
docker compose start

# View service status
docker compose ps

# View recent logs
docker compose logs --tail 100

# Apply source updates and rebuild
docker compose up --build -d
```

Do not use `docker compose down -v` unless you deliberately intend to delete the local database and Redis data.

## Ports and common problems

- Website: `http://localhost:3000`.
- API docs: `http://localhost:8010/docs`.
- WebSocket origin: `ws://localhost:8010`.
- PostgreSQL and Redis stay inside the Docker network; no database ports are exposed to the host.
- If port 8010 is occupied, change `API_PORT` and `NEXT_PUBLIC_WS_ORIGIN` together in `.env`, then rebuild.
- If port 3000 is occupied, stop the application using it, or deliberately change the web host port in Compose and `APP_ORIGIN` in `.env`. The helper script assumes port 3000; use the manual flow for a custom port.
- Use `localhost` consistently, not `127.0.0.1`, because the configured origin protects authenticated actions.
- A QR link pointing at localhost only works on the same computer. Phones need a reachable test hostname and a matching origin/WebSocket configuration. The supplied setup is intentionally local-only.
- Do not change `POSTGRES_PASSWORD` after the database volume has been initialized without also updating the PostgreSQL user's password. An existing database does not automatically pick up a new `.env` password.
- If startup fails, inspect `docker compose logs api migrate web --tail 100`. A successful `migrate` container exits with code 0; that is normal.

## Verification limits

The backend test suite and Next.js build passed, and the main teaching flow was checked in a browser against a disposable local fixture. Docker startup and real PostgreSQL/Redis integration were not executed on the development machine because those services were unavailable. Treat the first Docker run as an integration check, not a certified production deployment.
