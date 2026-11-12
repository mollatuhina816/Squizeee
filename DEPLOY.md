# Quizeee Production Deployment & In-Place Upgrade Guide

**Target Domain:** `https://bdattest.com`  
**Hostinger VPS IP:** `31.97.235.2`  
**Repository:** `https://github.com/mollatuhina816/Squizeee.git`

This guide covers upgrading the live production deployment of **Quizeee** on your Hostinger VPS **in-place**, preserving all existing PostgreSQL data (`users`, `organizations`, `presentations`, `slides`, `live_sessions`, `participants`, `answers`, `scheduled_quizzes`, etc.) and Redis volumes.

---

## Golden Rules to Protect Your Existing Database

1. **NEVER run `docker compose down -v` or `docker volume rm`** — the `-v` flag deletes the `postgres-data` and `redis-data` Docker volumes.
2. **NEVER change `POSTGRES_PASSWORD` in `.env` on the VPS** — PostgreSQL only reads `POSTGRES_PASSWORD` when a volume is first created. Changing it later will cause authentication errors until reverted.
3. **NEVER commit `.env` to Git** — keep local development secrets separate from your VPS `.env`.

---

## What Database Changes Are Applied in This Release?

The Alembic migration chain from the previous release (`b742ce812a03`) to the current head (`c619a4f20b71`) is **100% additive and non-destructive** (no tables or columns are dropped):

| Revision | Description | Schema Operations |
| :--- | :--- | :--- |
| `c853df923b04` | Live engagement, moderation & audience votes | Adds `live_settings`, `paused_at`, `revealed` to `live_sessions`; adds `team` to `participants`; creates `audience_questions` and `audience_votes` tables |
| `d964ea034c15` | Rotating refresh sessions | Adds `remember_me` to `auth_sessions`; creates `refresh_tokens` table |
| `ea75fb145d26` | Name-based student entry | Makes `participant_profiles.email` nullable (`DROP NOT NULL`) |
| `fb86ac256e37` | Saved live options | Adds `live_settings` JSON column to `presentations` |
| `9d47e02c61ab` | Participant stream & semester | Adds `stream` and `semester` columns to `participants` |
| `c619a4f20b71` | Participant institute name | Adds `institution_name` column to `participants` |

---

## Step 1: Push the Updated Code from Your Local Machine (Windows)

Open PowerShell in `D:\Quizeee`:

```powershell
cd D:\Quizeee

# 1. Remove any stray frontend/.env file if present (AI keys belong only in root .env)
if (Test-Path .\frontend\.env) { Remove-Item .\frontend\.env }

# 2. Stage all project updates
git add .

# 3. Verify that .env is NOT staged
git status

# 4. Commit and push to GitHub
git commit -m "Production release: live engagement, smart import, refresh sessions, and student details"
git push origin main
```

---

## Step 2: Connect to Your Hostinger VPS & Create a Safety Snapshot

SSH into your Hostinger VPS:

```bash
ssh root@31.97.235.2
```

Navigate to your deployed project directory (for example `/root/Squizeee`, `/opt/quizeee`, or `/var/www/quizeee` — check with `docker compose ls` if unsure):

```bash
docker compose ls
cd /path/to/your/quizeee-folder
```

Create a read-only SQL backup file on the VPS disk **before** pulling or migrating (this does **not** delete, stop, or alter your running database; it simply saves a restore point in `/root/`):

```bash
docker compose exec -T postgres pg_dump -U quizeee -d quizeee > ~/quizeee_pre_upgrade_$(date +%F_%H%M).sql
ls -lh ~/quizeee_pre_upgrade_*.sql
```

---

## Step 3: Pull the Latest Code on the VPS

From the project directory on the VPS:

```bash
git fetch origin
git pull origin main
```

*(If `git pull` warns about local untracked or modified files on the VPS, inspect them with `git status` first).*

---

## Step 4: Verify Production `.env` Settings on the VPS

Open `.env` on the VPS:

```bash
nano .env
```

Ensure the following variables are present (keep your existing `POSTGRES_PASSWORD` and `JWT_SECRET` unchanged!):

```dotenv
# Keep your existing POSTGRES_PASSWORD and JWT_SECRET as they are!
POSTGRES_PASSWORD=<your-existing-postgres-password>
JWT_SECRET=<your-existing-jwt-secret>

# Production origin and environment
APP_ORIGIN=https://bdattest.com
ENVIRONMENT=production
API_PORT=8010
NEXT_PUBLIC_WS_ORIGIN=wss://bdattest.com

# AI Question Generation & Smart Document Import
AI_PROVIDER=gemini
GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_QUESTION_MODEL=gemini-2.5-flash-lite
OPENAI_API_KEY=<your-openai-api-key-if-used>
OPENAI_QUESTION_MODEL=gpt-4.1-mini
AI_MAX_QUESTIONS_PER_REQUEST=20
AI_MAX_TEXT_LENGTH=20000
AI_MAX_IMAGE_SIZE_MB=10
AI_REQUEST_TIMEOUT_SECONDS=45
AI_MAX_OUTPUT_TOKENS=8000
AI_DAILY_LIMIT_FACULTY=50
AI_DAILY_LIMIT_ADMIN=100
AI_DAILY_LIMIT_FACULTY_LITE=10
AI_REQUESTS_PER_MINUTE=5
IMPORT_AI_MAX_CONTEXT_CHARS=350000
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## Step 5: Build & Deploy In-Place (Keeping Existing Database)

Run Docker Compose to rebuild the `migrate`, `api`, `worker`, and `web` images and apply the new database migrations automatically:

```bash
docker compose up --build -d
```

What happens during this command:
1. `postgres` and `redis` continue using their existing `postgres-data` and `redis-data` volumes.
2. `migrate` runs `alembic upgrade head` against the existing database and exits with `0` once schema updates finish.
3. `api`, `worker`, and `web` recreate and start with the newly built code once `migrate` succeeds.

---

## Step 6: Verify the Deployment

1. **Check container statuses:**
   ```bash
   docker compose ps -a
   ```
   - `postgres`, `redis`, `api`, `worker`, and `web` should show `Up` / `healthy`.
   - `migrate` should show `Exited (0)`.

2. **Check migration logs:**
   ```bash
   docker compose logs migrate --tail 50
   ```
   You should see Alembic upgrading through `c619a4f20b71`.

3. **Check API readiness:**
   ```bash
   curl -i http://127.0.0.1:8010/health/ready
   ```
   Expected output: `HTTP/1.1 200 OK` with `{"status":"ready"}`.

4. **Check Nginx / Reverse Proxy WebSocket & Upload Settings (If Applicable):**
   Because the new release supports up to 40 MB PDF/PPTX/DOCX imports and live WebSockets (`/api/v1/live/ws`), verify your Nginx site config (`/etc/nginx/sites-available/...`) includes:
   ```nginx
   client_max_body_size 50M;

   location /api/v1/live/ws {
       proxy_pass http://127.0.0.1:8010/api/v1/live/ws;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_set_header Host $host;
       proxy_set_header Origin $http_origin;
       proxy_read_timeout 120s;
   }
   ```
   If you edit Nginx config, test and reload with:
   ```bash
   nginx -t && systemctl reload nginx
   ```

5. **Smoke Test in Browser:**
   - Open `https://bdattest.com/` and sign in with an existing account.
   - Open `https://bdattest.com/admin` (with your super-admin account) to confirm all existing teachers, students, organizations, and participant records are present.
   - Open `https://bdattest.com/join` to verify the new Institute Name, Stream, Semester, and Name/Email entry fields.

---

## Troubleshooting & Rollback

- **View live logs if an error occurs:**
  ```bash
  docker compose logs api web worker --tail 100
  ```
- **Check current database migration revision:**
  ```bash
  docker compose exec api alembic current
  ```
- **Emergency database restore (only if ever needed):**
  ```bash
  cat ~/quizeee_pre_upgrade_YYYY-MM-DD_HHMM.sql | docker compose exec -T postgres psql -U quizeee -d quizeee
  ```
