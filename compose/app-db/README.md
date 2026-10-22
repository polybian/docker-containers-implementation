# app-db stack

Python app + Postgres on an **internal** bridge network (`appnet`).

## Run it (on a Docker host)

```bash
cp .env.app.example .env.app && cp .env.db.example .env.db
# then fill in POSTGRES_USER / POSTGRES_PASSWORD in .env.db
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

## Design notes

- **Database is not published.** There is no `ports:` on `db`, so Postgres is
  reachable only inside `appnet` (the app connects to `db:5432` via Docker's
  embedded DNS). From your laptop: `docker compose exec db psql -U <user> -d demodb`.
- **App waits for a healthy DB**, not just a started container
  (`depends_on` + `service_healthy` on the `pg_isready` healthcheck).
- **Data lives in the named volume `pgdata`** -- it survives
  `docker compose down`. Backup/restore procedure: `docs/volumes-backup.md`.
- **Secrets come from `.env.app` / `.env.db`** (gitignored), never baked into
  the image -- see `docs/image-security.md`. Env files are split per service
  so the app never sees `POSTGRES_PASSWORD` and the db never sees app vars.
