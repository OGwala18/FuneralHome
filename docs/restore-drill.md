# Restore drill: proving the daily backup

Supabase's free tier keeps no backups. The `jobs` cron (`backend/app/jobs/daily.py`)
runs `db/backup.py` each morning and writes one gzip JSON file per day to its
private Railway volume, keeping 30. A backup nobody has restored is only a hope.
This page shows how to restore one into a **scratch** database and check it.

`db/restore.py` does the work. It:

- refuses if the target has any row in `people`, `policies`, `plan_enquiries` or
  `staff_users`, or if the target is the same as `DATABASE_URL` /
  `DATABASE_OWNER_URL`. It cannot overwrite a live book;
- builds the schema with `db/migrate.py` up to the backup's own newest migration
  (further if the backup needs a table or column that comes later), loads every
  table in foreign-key order in **one transaction** with user triggers off, so
  `updated_at` stamps, audit and history rows (`member_book_history`, 0031) come
  back as they were and nothing is recorded twice;
- checks every table row by row against the file before it commits. Any
  difference rolls the whole load back;
- then runs the newer migrations over the restored rows (`--no-forward` skips this).

It prints table names and counts only. The file holds ID numbers: keep it out
of the repository, out of chat, and off shared drives, and delete it afterwards.

## Proven locally on 16 Nov 2026

The local Docker dev database (`induduzo-db`, test data) was backed up with
`db/backup.py` and restored into two new scratch databases in the same
container:

- **Stopped at the backup's schema (`--no-forward`):** 32 tables, 473 rows
  loaded. Every table, and both views, matched the source on row count and on
  an MD5 checksum of every row, all columns included (so the `updated_at`
  stamps survived with triggers off).
- **Brought forward:** the 10 newer migrations (0021 to 0030) ran over the
  restored rows. Every member-book table still matched. `ref_branches` and
  `ref_plan_prices` gained the rows that 0023 and 0024 add, as they should.
- **Refusals:** a second restore over the restored book, a restore over the dev
  book, and a target equal to `DATABASE_URL` were all refused, with nothing written.

Both scratch databases were dropped and the backup file deleted.

**Re-run the same evening, after 0031 (`member_book_history`) shipped:** a
backup of the dev book (at 0019) restored and was brought forward through 0031
with no history rows invented by the load. Two edits were then made in that
copy, so it held history rows, and it was backed up and restored again into a
second empty database: 35 tables, 481 rows, every table identical to the file;
`people` and `member_book_history` matched on an MD5 of every row, and the
history table's id counter was moved past the restored rows. Both scratch
databases were dropped and the files deleted.

**A drill against a real production backup has not been done.** It needs the
owner: they hold the Railway login, and the file contains members' ID numbers.

## The drill against a production backup (owner)

Do it on the office laptop, with the local Docker stack running
(`docker compose up -d`). Never restore into Supabase or Railway for a drill.

### 1. Copy one backup off the `jobs` volume

With the Railway CLI, logged in as the owner, from the repository folder:

```bash
railway link
```

Choose project **induduzo**, environment **production**, service **jobs**.
Then list the files and download the newest into a folder **outside** the repo:

```bash
railway volume files list /
```

```bash
railway volume files download /induduzo-2026-11-16T0600Z.json.gz "%USERPROFILE%\Downloads\induduzo-restore\induduzo-2026-11-16T0600Z.json.gz"
```

Use the real file name from the list. Railway lists paths from the volume's
root, so the file shows as `/induduzo-...`, not `/backups/induduzo-...`.
`railway volume browse /` does the same in an interactive screen. (These
commands come from Railway's documentation and have not been run against our
project yet. If the CLI asks which volume, pick the one attached to `jobs`.)

Note the line the same morning's `jobs` log printed:
`Backup induduzo-...json.gz: N tables, M rows; people=P, policies=Q`.

### 2. Make a scratch database

```bash
docker exec induduzo-db psql -U induduzo -d postgres -c "create database induduzo_restore_check"
```

### 3. Restore it

In PowerShell, from the repository folder, with the backend's Python (it has
`psycopg`). Use the local password from `.env` (`POSTGRES_PASSWORD`):

```powershell
$env:RESTORE_DATABASE_URL = "postgresql://induduzo:<local password>@localhost:5433/induduzo_restore_check"
backend\.venv\Scripts\python.exe db\restore.py "$env:USERPROFILE\Downloads\induduzo-restore\induduzo-2026-11-16T0600Z.json.gz" --dry-run
backend\.venv\Scripts\python.exe db\restore.py "$env:USERPROFILE\Downloads\induduzo-restore\induduzo-2026-11-16T0600Z.json.gz"
```

The drill passes when restore.py ends with `Restore complete.`, its first line
shows the same `people=` and `policies=` as the `jobs` log line, and it says
`every table identical to the file`.

### 4. Look, then throw it away

Optionally point a local API at the scratch database and open the local portal
to see the members. Then:

```bash
docker exec induduzo-db psql -U induduzo -d postgres -c "drop database induduzo_restore_check with (force)"
```

Delete the downloaded file and empty the Recycle Bin. Record the date of the
drill in `CLAUDE.md`.

## In a real disaster

The same command restores into a **new, empty** Supabase project (or any
Postgres). Run it from a laptop with `RESTORE_DATABASE_URL` set to the new
project's owner connection string. Then set the `induduzo_api` password
(`db/provision_api_role.py`), point Railway's `DATABASE_URL` and
`DATABASE_OWNER_URL` at it, and redeploy. Staff sign-ins live in Supabase Auth,
not in the backup, so each staff member needs a new sign-in (the `staff_users`
rows come back; their Supabase accounts do not).

## If restore.py refuses

- *"The target already has rows in ..."*: you pointed it at a database in use.
  Make a new empty one.
- *"the backup records migrations this checkout does not have"*: a note, not a
  refusal. The backup is from a renamed or newer migration. It still goes on if
  every table and column fits.
- *"Even with every migration in this checkout, the target lacks ..."*: the
  backup is newer than your checkout. `git pull` the branch production runs (`main`).
- *"Loading X failed: UniqueViolation, constraint ..."* (or similar): the kind of
  error and the constraint are shown. The row itself is never printed. Nothing
  was kept.
