# Update bdattest.com on the VPS while preserving production data

This procedure is based on this repository's `compose.yaml` and `DEPLOY.md`.
The recorded server is `31.97.235.2`, the site is `https://bdattest.com`, and the Git remote is `https://github.com/mollatuhina816/Squizeee.git`.
These details have not been verified against the live VPS. Confirm them before running commands.

The latest department deletion, session reports, import UI/parser, and question time/marks changes add **no migration files**. The local migration head is `c619a4f20b71`. A VPS on an older release can still need existing migrations: compare its revision before applying them.

No deployment can promise zero loss under every possible failure. Preserve the current database volume, make and test a backup, keep an off-server copy, and avoid writes during the final backup/update window.

## 1. Prepare and push the code from Windows

Run in PowerShell:

```powershell
cd D:\Quizeee1\quizeee
git status --short
git diff --stat
git branch --show-current
git remote -v
```

Review the changes you intend to release. The current checkout contains unrelated local database dumps and helper scripts. Do not use `git add .`.

Stage the tracked changes and the known new feature files explicitly:

```powershell
git add -u
git add -- backend/app/import_answers.py backend/app/structured_import.py
git add -- backend/tests/test_import_recovery.py backend/tests/test_structured_import.py backend/tests/test_teacher_records.py
git add -- frontend/app/question-importer.css frontend/app/quiz-settings.css frontend/app/session-records.css
git add -- docs/PDF_IMPORT_FLOW.md docs/structured-import.md docs/BDATTEST_SAFE_UPDATE.md
git diff --cached --stat
git diff --cached --name-only
```

`git add -u` stages all tracked modifications/deletions. Review the staged diff and unstage anything outside the release with `git restore --staged -- <path>`.

**Stop if the staged list contains `.env`, credentials, database dumps, local backups, or personal data.** The SQL schema examples already tracked under `docs/` are distinct from database backups. Never upload your Windows `.env` files to overwrite the production configuration.

Validate before pushing:

```powershell
node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
Push-Location backend
.\venv\Scripts\python.exe -m pytest tests/test_teacher_records.py tests/test_permissions.py tests/test_scheduled.py tests/test_builder_live.py tests/test_import_recovery.py tests/test_structured_import.py tests/test_smart_import.py tests/test_document_import.py -q
Pop-Location
```

Check exit codes and resolve failures. A skipped test requiring an unavailable optional tool must be understood, not treated as successful coverage.

```powershell
git commit -m "Add teacher session records, department deletion, quiz settings and PDF import improvements"
git push origin main
git rev-parse HEAD
```

Keep the full commit hash. This is the release to deploy. No commit or push has been performed for you by creating this guide.

## 2. Identify the existing production deployment

Connect from Windows:

```powershell
ssh root@31.97.235.2
```

The commands below run in **Bash on the Linux VPS**, not Windows PowerShell.

```bash
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

Find the current PostgreSQL container for bdattest.com. Substitute its actual name:

```bash
PG_CONTAINER='REPLACE_WITH_EXISTING_POSTGRES_CONTAINER_NAME'
docker inspect "$PG_CONTAINER" --format '{{ index .Config.Labels "com.docker.compose.project" }}'
docker inspect "$PG_CONTAINER" --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
docker inspect "$PG_CONTAINER" --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}'
docker inspect "$PG_CONTAINER" --format '{{range .Mounts}}{{println .Type .Name .Source "->" .Destination}}{{end}}'
```

Record the existing project name, working directory, Compose files, and PostgreSQL mount name. Use that same directory and project throughout. A new project name can create a new empty volume and make the database appear lost.

Set the verified values. Substitute the actual production directory and project name:

```bash
APP_DIR='/REPLACE/WITH/EXISTING/PROJECT/DIRECTORY'
PROJECT='REPLACE_WITH_EXISTING_COMPOSE_PROJECT_NAME'
cd "$APP_DIR"
COMPOSE_ARGS=(-p "$PROJECT" -f "$APP_DIR/compose.yaml")
dc() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }
dc ps -a
```

If the inspected deployment uses additional Compose files, append **all those same files in their original order** to `COMPOSE_ARGS`, e.g. `COMPOSE_ARGS+=(-f "$APP_DIR/compose.production.yaml")`. Preserve the original env-file flags too. Do not continue with a different configuration or a different database service. This guide expects the existing service names `postgres`, `redis`, `migrate`, `api`, `worker`, and `web`.

Confirm this selects the exact PostgreSQL container identified above:

```bash
dc ps -q postgres
docker inspect "$PG_CONTAINER" --format '{{.Id}}'
dc exec -T postgres psql -U quizeee -d quizeee -c 'SELECT current_database(), version();'
dc exec -T api alembic current
```

The two container IDs must match. If production uses another database user/name, substitute those values in every backup and database command below.

## 3. Capture a recovery point and existing app images

Finish active quizzes first. Plan a maintenance window: restarting the API interrupts live connections. Keep the same SSH session open so the variables and `dc` function remain available.

```bash
umask 077
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="/root/quizeee-backups/$STAMP"
mkdir -p "$BACKUP"
printf '%s\n' "$BACKUP"
git rev-parse HEAD > "$BACKUP/previous-commit.txt"
git status --short > "$BACKUP/previous-git-status.txt"
cp -p .env "$BACKUP/production.env"
cp -p compose.yaml "$BACKUP/compose.yaml"
docker inspect "$(dc ps -q postgres)" --format '{{range .Mounts}}{{println .Type .Name .Source "->" .Destination}}{{end}}' > "$BACKUP/postgres-mounts-before.txt"
dc exec -T api alembic current > "$BACKUP/migration-before.txt"
df -h . /root
docker system df
```

Back up additional production Compose/env files, reverse proxy configuration, and any uploaded-file bind mounts/object storage separately. The `.env` copy contains secrets: keep the backup private. The repository's default database stores quizzes and responses in PostgreSQL; do not assume a customized server has no extra file storage.

Retain the exact running app images for an immediate rollback:

```bash
printf 'services:\n' > "$BACKUP/rollback-images.yaml"
for service in api worker web; do
  container=$(dc ps -q "$service")
  test -n "$container" || { echo "Missing running service: $service"; break; }
  image=$(docker inspect "$container" --format '{{.Image}}')
  tag="quizeee-rollback-$service:$STAMP"
  docker image tag "$image" "$tag" || break
  printf '  %s:\n    image: %s\n' "$service" "$tag" >> "$BACKUP/rollback-images.yaml"
done
cat "$BACKUP/rollback-images.yaml"
```

Verify all three service entries are present. Do not prune images or volumes during the release. A VPS provider snapshot before updating is an additional recovery layer, not a substitute for the tested database dump below.

## 4. Fetch the release and build before downtime

```bash
git status --short
git fetch origin
git log --oneline HEAD..origin/main
git diff --stat HEAD origin/main
git diff HEAD origin/main -- compose.yaml backend/migrations
```

If tracked production files are modified, reconcile them first. Do not use `git reset --hard`, `git clean`, or overwrite production `.env` to make a pull work.

Use the full release hash saved from Windows:

```bash
RELEASE_COMMIT='REPLACE_WITH_FULL_COMMIT_HASH'
git merge --ff-only "$RELEASE_COMMIT"
test "$(git rev-parse HEAD)" = "$RELEASE_COMMIT"
dc config --quiet
```

Stop if the commit check or configuration validation fails. Verify that the PostgreSQL image major version, credentials, database name, mount, service configuration and Compose project remain unchanged. Do not combine this release with a PostgreSQL upgrade.

Keep existing `POSTGRES_PASSWORD`, `JWT_SECRET`, AI keys and production URLs. Expected URLs for this deployment are:

```dotenv
APP_ORIGIN=https://bdattest.com
ENVIRONMENT=production
NEXT_PUBLIC_WS_ORIGIN=wss://bdattest.com
```

Build just the app images while the old containers still serve traffic:

```bash
dc build migrate api worker web
```

Continue only on success. This builds Linux images using the repository's dependency lock and Dockerfiles; it does not use your Windows virtual environment or `node_modules`. If a dependency or production build fails, fix it before stopping the live application.

## 5. Stop app writes, back up PostgreSQL, and test the backup

Only after the build succeeds, stop the app services. Keep PostgreSQL and Redis running:

```bash
dc stop web api worker
```

The site will be unavailable during this maintenance window. Stop any additional services/scripts that write to this database too. The reverse proxy can serve your existing maintenance page if configured.

Capture the database in custom format inside the container and copy it out. Run each command separately and continue only if it succeeds:

```bash
dc exec -T postgres pg_dump -U quizeee -d quizeee -Fc -f "/tmp/quizeee-$STAMP.dump"
dc cp "postgres:/tmp/quizeee-$STAMP.dump" "$BACKUP/database.dump"
test -s "$BACKUP/database.dump"
dc exec -T postgres pg_restore --list "/tmp/quizeee-$STAMP.dump" > "$BACKUP/archive-contents.txt"
dc exec -T postgres pg_dumpall -U quizeee --globals-only > "$BACKUP/globals.sql"
sha256sum "$BACKUP/database.dump" > "$BACKUP/database.sha256"
ls -lh "$BACKUP/database.dump" "$BACKUP/globals.sql"
```

`pg_dump` produces a consistent database snapshot. The custom archive is restored with `pg_restore`. The global backup includes database roles; protect it as sensitive data. See the official [pg_dump documentation](https://www.postgresql.org/docs/16/app-pgdump.html).

Save exact counts for every current public table:

```bash
cat > "$BACKUP/counts.sql" <<'SQL'
SELECT format('SELECT %L AS table_name, count(*) AS rows FROM %I.%I;', tablename, schemaname, tablename)
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename
\gexec
SQL
dc exec -T postgres psql -X -At -v ON_ERROR_STOP=1 -U quizeee -d quizeee < "$BACKUP/counts.sql" > "$BACKUP/counts-before.txt"
```

**Test a full restore into a NEW, separate database. Do not restore into `quizeee`.** Ensure there is sufficient disk space for the second database:

```bash
CHECK_DB="quizeee_verify_$STAMP"
dc exec -T postgres createdb -U quizeee "$CHECK_DB"
dc exec -T postgres pg_restore -U quizeee -d "$CHECK_DB" --no-owner --no-acl --single-transaction --exit-on-error "/tmp/quizeee-$STAMP.dump"
dc exec -T postgres psql -X -At -v ON_ERROR_STOP=1 -U quizeee -d "$CHECK_DB" < "$BACKUP/counts.sql" > "$BACKUP/counts-restored.txt"
diff -u "$BACKUP/counts-before.txt" "$BACKUP/counts-restored.txt"
```

Every command must succeed, and `diff` should print no differences. Keep the verification database until the release is accepted; it consumes additional storage.

Download an off-server copy in a second **Windows PowerShell** terminal. Replace the directory with the exact `BACKUP` path printed earlier:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\QuizeeeBackups"
scp root@31.97.235.2:/root/quizeee-backups/REPLACE_TIMESTAMP/database.dump "$env:USERPROFILE\Documents\QuizeeeBackups\database-REPLACE_TIMESTAMP.dump"
Get-FileHash "$env:USERPROFILE\Documents\QuizeeeBackups\database-REPLACE_TIMESTAMP.dump" -Algorithm SHA256
```

Compare this hash with the VPS `database.sha256` file. Do not add this backup to Git.

If backup/restore verification fails, do not migrate. Restart the old tagged app images using step 8, investigate, and reschedule the release.

## 6. Apply migrations, then start only application services

Check target heads using the newly built image:

```bash
dc run --rm --no-deps migrate alembic heads
dc run --rm --no-deps migrate alembic current
```

If the live revision is already the target head, the following upgrade is a no-op. If it is behind, review every pending migration and test it against a copy first. Do not infer safety just because the newest features need no migration.

```bash
dc run --rm --no-deps migrate alembic upgrade head
```

Continue only if it exits successfully. On failure, keep the site in maintenance and inspect the database revision and logs; do not run a downgrade or overwrite the live database.

```bash
dc up -d --no-deps api worker
```

Wait for API readiness. This assumes the existing host API port is 8010; use the actual port if customized:

```bash
curl --fail --show-error http://127.0.0.1:8010/health/ready
dc logs --tail 60 api worker
```

Repeat the readiness request until it returns HTTP 200. Then start the web service:

```bash
dc up -d --no-deps web
dc ps -a
curl --fail --show-error --output /dev/null http://127.0.0.1:3000/
curl --fail --show-error --output /dev/null https://bdattest.com/
```

These commands target `api`, `worker`, and `web`, preserving the existing database/Redis containers. Compose recreates changed app containers while preserving mounted volumes; see [Docker Compose up](https://docs.docker.com/reference/cli/docker/compose/up/).

## 7. Verify records and new features

Check the database mount is unchanged:

```bash
docker inspect "$(dc ps -q postgres)" --format '{{range .Mounts}}{{println .Type .Name .Source "->" .Destination}}{{end}}' > "$BACKUP/postgres-mounts-after.txt"
diff -u "$BACKUP/postgres-mounts-before.txt" "$BACKUP/postgres-mounts-after.txt"
dc exec -T api alembic current
dc logs --tail 100 api web worker
```

You can capture post-update counts using the same `counts.sql`. Once the app starts, background expiry tasks and real users can legitimately create or update records, so counts are evidence to investigate, not a reason to overwrite production. For this release, without pending schema migrations, existing user/quiz records should remain present.

In the browser, sign in using an existing teacher account and verify:

1. Existing departments, quizzes, students and session records are present.
2. **Session records** lists old live sessions and assigned quizzes. Expand a student and compare their submitted answer with the right answer, result, explanation and marks.
3. Upload a test PDF, keep valid rows, and import it into a disposable test quiz.
4. Set individual and bulk question time/marks, save, and reload. Confirm totals.
5. Assign a disposable test quiz and check its countdown and results.
6. Create an empty **test department**, then delete that test department. Do not delete a real department merely to test the button.
7. Verify a live quiz joins and WebSockets work.

Do not change DNS, TLS or reverse proxy routes if they already work. For large document imports, the existing proxy must allow at least a 40 MB upload plus request overhead (e.g. `client_max_body_size 50M` for Nginx) and an appropriate processing timeout. Test any edited Nginx config with `nginx -t` before reloading it.

Keep the database backup, verified off-server copy, old image tags, production configuration and previous commit until the release is accepted and routine backups are confirmed.

## 8. Roll back the application if the release fails

Keep using the same `APP_DIR`, `PROJECT`, `COMPOSE_ARGS`, `BACKUP` and `STAMP` values. If SSH disconnected, reconstruct them from the saved backup directory and the original production configuration.

For this feature release, if no incompatible migrations were applied, use the saved app image overrides:

```bash
dc stop web api worker
docker compose "${COMPOSE_ARGS[@]}" -f "$BACKUP/rollback-images.yaml" up -d --no-deps --no-build --force-recreate api worker
curl --fail --show-error http://127.0.0.1:8010/health/ready
docker compose "${COMPOSE_ARGS[@]}" -f "$BACKUP/rollback-images.yaml" up -d --no-deps --no-build --force-recreate web
```

Wait for API readiness before starting the old web image. This rollback uses the **current production database**, preserving data written since deployment. It does not rebuild from the working tree, and does not remove volumes. Keep using the override while investigating; a plain `dc up` can switch back to the newly built images.

If migrations changed the schema incompatibly, image rollback alone may not work. Stop and prepare a schema-specific recovery plan. Do not automatically downgrade Alembic or restore an old dump over the live database.

## 9. Database recovery is separate from application rollback

A database restore replaces a point in time. Any writes made after that backup would be absent. There is no command that can blindly overwrite the live database and also guarantee preservation of later writes.

If corruption/data loss actually occurs:

1. Stop application writers and keep maintenance active.
2. Back up the current database, even if damaged, so newer records are not discarded.
3. Restore the verified backup into another separate database, as tested in step 5.
4. Compare the databases and reconcile newer records with qualified database help.
5. Switch application connections only after validating the recovery database and preserving the originals.

Do not pipe an old SQL dump into the existing populated `quizeee` database. See the official [pg_restore documentation](https://www.postgresql.org/docs/16/app-pgrestore.html) for archive restoration options.

## Commands/settings to avoid during this update

- `docker compose down -v`, `docker volume rm`, and volume pruning.
- A new Compose project name, a different deployment folder, or a changed PostgreSQL volume mapping.
- Replacing production `.env` with your Windows `.env`.
- Changing `POSTGRES_PASSWORD`, `JWT_SECRET`, database name or PostgreSQL major version as part of this feature release.
- Uploading a local database dump as the new production database.
- Running `git add .` while local database backups are in the repository folder.
- Restoring a backup over the live database as a routine deployment step.

This guide documents the process only. It has not connected to the VPS, pushed code, taken a production backup, or deployed the release.
