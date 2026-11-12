# Quizeee — Next Tasks & Production Roadmap

This document outlines the immediate post-deployment verification steps for `https://bdattest.com` (`31.97.235.2`) followed by the prioritized feature and engineering tasks for the next milestone.

---

## 1. Immediate Post-Deployment Tasks (Hostinger VPS `31.97.235.2`)

- [ ] **Execute In-Place Upgrade ([DEPLOY.md](DEPLOY.md)):**
  - SSH into `root@31.97.235.2`, take a `pg_dump` snapshot (`~/quizeee_pre_upgrade_*.sql`), pull `origin/main`, and run `docker compose up --build -d`.
- [ ] **Verify Database Migration (`c619a4f20b71`):**
  - Confirm `docker compose ps -a` shows `migrate` exited with code `0` and `docker compose exec api alembic current` reports `c619a4f20b71 (head)`.
- [ ] **Verify Nginx Reverse Proxy Configuration:**
  - Ensure `client_max_body_size 50M;` is set for 40 MB PDF/PPTX/DOCX imports.
  - Ensure `/api/v1/live/ws` forwards `Upgrade` and `Connection "upgrade"` headers with `proxy_read_timeout 120s`.
  - Ensure `X-Forwarded-For` / `X-Real-IP` headers are trusted if rate-limiting behind Nginx.
- [ ] **Automated Daily Database Backups on VPS:**
  - Add a cron job on the VPS (`crontab -e`) to dump PostgreSQL daily and retain the last 14 days:
    ```cron
    0 2 * * * cd /path/to/quizeee && docker compose exec -T postgres pg_dump -U quizeee -d quizeee | gzip > /root/backups/quizeee_$(date +\%F).sql.gz && find /root/backups/ -name "quizeee_*.sql.gz" -mtime +14 -delete
    ```

---

## 2. Priority Feature & Product Tasks (Next Milestone)

### Priority 1: Account Recovery & Email Lifecycle
- [ ] **Password Reset Flow:** Add `POST /api/v1/auth/forgot-password` and `POST /api/v1/auth/reset-password` with time-limited, single-use hashed tokens and SMTP/transactional email delivery.
- [ ] **Email Verification:** Verify newly registered teacher and student email addresses before granting organization-wide privileges.
- [ ] **Organization Member Invitations:** Allow Organization Owners and Admins to invite teachers by email and assign their initial role (`admin`, `department_admin`, `faculty`, `faculty_lite`) and department.

### Priority 2: Question Bank Full Lifecycle Management
- [ ] **Edit & Delete Bank Questions:** Add `PATCH /api/v1/organizations/{org_id}/bank/questions/{question_id}` and `DELETE /api/v1/organizations/{org_id}/bank/questions/{question_id}` endpoints and wire Edit/Delete actions into [`frontend/app/bank/[org]/page.tsx`](frontend/app/bank/%5Borg%5D/page.tsx).
- [ ] **Bulk Selection & Export:** Support bulk tag/subject updates, bulk deletion, and CSV/JSON export directly from the Question Bank.
- [ ] **Department-Shared Question Banks:** Allow faculty within the same department to share and reuse department-scoped question banks.

### Priority 3: Super-Admin & Organization Administration Controls
- [ ] **Super-Admin Account Actions:** Add audited controls in [`frontend/app/admin/page.tsx`](frontend/app/admin/page.tsx) to activate/deactivate accounts (`User.active`), revoke active sessions, and export participant directories to CSV/XLSX.
- [ ] **Organization Settings UI:** Surface the existing backend endpoints (`GET/PATCH /api/v1/organizations/{org_id}/settings`, `PATCH /members/{membership_id}`, and `GET /audit`) in the teacher workspace UI so Owners can configure `faculty_lite` permissions, change member roles, and view audit logs without API calls.

### Priority 4: Expanded Question Types in Scheduled Quizzes
- [ ] **Scheduled Quiz Format Parity:** Extend [`backend/app/scheduled_routes.py`](backend/app/scheduled_routes.py) and [`frontend/app/quiz/[id]/page.tsx`](frontend/app/quiz/%5Bid%5D/page.tsx) to support `ranking` and `hotspot` questions in addition to `mcq`, `multiple_select`, `true_false`, `short_answer`, and `quiz`.

### Priority 5: Background Workers, Scalability & Observability
- [ ] **Move Quiz Expiry Sweep to Celery Beat / Distributed Task:** Replace the per-process `expire_quizzes` loop in [`backend/app/main.py`](backend/app/main.py) with a scheduled Celery task so multi-worker deployments run a single coordinated sweep.
- [ ] **Async Report & Document Jobs:** Offload large PDF/PNG analytics exports and heavy document-import conversions to the Celery worker queue (`backend/app/worker.py`).
- [ ] **Real PostgreSQL & Redis CI Pipeline:** Add a GitHub Actions workflow (`.github/workflows/ci.yml`) with PostgreSQL and Redis service containers to run `pytest` (including `QUIZEEE_TEST_POSTGRES_URL` concurrency tests), `alembic upgrade head`, `pnpm typecheck`, and `node --test frontend/tests/*.test.mjs` on every push.
