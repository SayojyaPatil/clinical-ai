# Stage 1 persistence and migrations

Run from the repository root, using the project virtual environment:

```sh
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/python -m app.migrate --database clinical_notes.db
```

Application startup initializes fresh databases through Alembic. Existing
databases must be upgraded explicitly with the command above before startup;
a pending revision fails startup with an actionable message, without modifying
existing data. This prevents development reloads from applying migrations.
No OpenAI calls or authentication secrets are required by the migration command.
Do not use `create_all()` to upgrade existing databases or stamp an uninspected
schema. The supported initial schema is the original notes/users schema, with or
without the nullable `owner_username` column. Unexpected schemas fail closed.

Before any pending migration, the runner holds a SQLite write reservation,
creates a unique backup through SQLite's backup API (including committed WAL
content), verifies backup integrity, and only then runs transactional DDL and
backfill. Backup failure aborts migration. The runner is idempotent at head.
SQLite files are restricted to mode 0600; newly created backup directories use
0700. Backups live in the database's adjacent `backups/` directory; the project
root backup directory is ignored by Git. Keep backups private.

## Data semantics

- Existing note IDs, timestamps, user records and owners are never rewritten.
- Missing ownership is not inferred or assigned. New review actors must own the
  parent note; review revision references must belong to the same note.
- New analyses store validated structured AI JSON, model/prompt/schema versions,
  the existing comma-joined response fields, source metadata, and unreviewed state
  in one transaction. Persistence failure rolls back the entire analysis.
- Submitted text remains exactly in immutable `notes.note_text`. Source metadata
  records its UTF-8 byte size/hash. Images remain byte-for-byte validated BLOBs,
  with MIME type, original filename, byte size, SHA-256, and storage timestamp.
  Filenames are untrusted metadata, never filesystem paths. No source is served
  publicly and no source/review endpoints are added in this stage.
- Image MIME/content/size/pixel checks remain in `app/image_validation.py` before
  AI execution or persistence. Limits remain PNG/JPEG/WebP, 5 MiB, 20M pixels.
- Historical AI JSON and model provenance stay SQL NULL: flattened lists cannot
  be reconstructed losslessly. Historical image markers (including ambiguous
  text starting `[Image upload]`) are classified unknown/unavailable, without
  bytes, inferred MIME, invented hashes or filenames. Their stored text remains
  untouched. Other legacy text has inferred text provenance.
- Backfill timestamps describe migration time, never original upload time.
- Original notes/sources and human revisions/events are append-only, protected
  against updates, deletes and replacement inserts. Review state is mutable,
  but no review UI, corrections, approvals or APIs are implemented yet.
- SQLite foreign keys are enabled on every application/migration connection.
  Enforce the same setting in any maintenance connection.

## Verification and recovery

```sh
SECRET_KEY=synthetic-test-secret OPENAI_API_KEY=synthetic-placeholder \
  venv/bin/python -m pytest -v
```

Tests use temporary SQLite databases and synthetic inputs; provider calls are
stubbed. They do not migrate or modify the application's local database.

Destructive Alembic downgrades are deliberately disabled. For recovery, stop the
application, retain the current database and its matching WAL/SHM files, restore
a verified backup into a **separate database path**, verify integrity and original
rows, and start a compatible application version using that restored database.
Do not overwrite a live database or discard newer records. If writes occurred
since the backup, reconcile them before switching databases.

An upgrade requires restart of already-running application processes to load the
new persistence code. No frontend response schema, auth flow, endpoint path, or
AI behavior is changed by Stage 1. Local file permissions provide access control,
not encryption at rest; this remains a synthetic-data demonstration application.
