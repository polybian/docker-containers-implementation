# app-db stack (LAB)

Python app + Postgres on an **internal** bridge network (`appnet`).

## Run it (on a Docker host)

```bash
cp .env.example .env      # then fill in POSTGRES_USER / POSTGRES_PASSWORD
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

## Design notes

- **Database is not published.** There is no `ports:` on `db`, so Postgres is
  reachable only inside `appnet` (the app connects to `db:5432` via Docker's
  embedded DNS). From your laptop: `docker compose exec db psql -U <user> -d labdb`.
- **App waits for a healthy DB**, not just a started container
  (`depends_on` + `service_healthy` on the `pg_isready` healthcheck).
- **Data lives in the named volume `pgdata`** -- it survives
  `docker compose down`. Backup/restore procedure: `docs/volumes-backup.md`.
- **Secrets come from `.env`** (gitignored), never baked into the image --
  see `docs/image-security.md`.
