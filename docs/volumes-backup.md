# Volumes vs bind mounts, and backing up a named volume (LAB)

## Volumes vs bind mounts

| | Named volume | Bind mount |
|---|---|---|
| What it is | Storage managed by Docker (`pgdata`) | A host path mounted into the container (`./data:/data`) |
| Created by | `volumes:` in compose, or `docker volume create` | Just exists on the host |
| Portability | Moves with `docker compose` anywhere | Tied to that host's path layout |
| Permissions | Docker initializes ownership sanely | Host UID/GID leaks in -- classic source of "permission denied" |
| Backups | Snapshot the volume (procedure below) | `cp`/`rsync` the directory |

**Rule:** databases and anything stateful -> **named volumes** (this repo's
`pgdata`, `promdata`, `grafanadata`). Bind mounts are for *config* you edit
(`./prometheus.yml:/etc/prometheus/prometheus.yml:ro`) and *code* you iterate
on -- never for data you can't afford to lose.

## Backup procedure: named volume (step by step)

Back up `pgdata` from the app-db stack. The trick: you can't `tar` a volume
from the host directly, so you run a throwaway container that mounts the
volume and the backup destination side by side. No extra software on the host.

```bash
# 0. Pick a backup dir on the host and a timestamped name
BACKUP_DIR=~/backups
mkdir -p "$BACKUP_DIR"
STAMP=$(date +%F-%H%M)

# 1. (Recommended) stop writers so the backup is consistent.
#    For Postgres this avoids a torn backup. Reads can stay up.
docker compose -f compose/app-db/docker-compose.yml stop app

# 2. Snapshot the volume with a throwaway alpine container.
#    --rm: the container deletes itself when done; nothing lingers.
docker run --rm \
  -v lab-app-db_pgdata:/data:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/pgdata-${STAMP}.tar.gz" -C /data .

# 3. Verify the archive is readable and non-empty.
tar tzf "$BACKUP_DIR/pgdata-${STAMP}.tar.gz" | head -5
ls -lh "$BACKUP_DIR/pgdata-${STAMP}.tar.gz"

# 4. Bring the stack back.
docker compose -f compose/app-db/docker-compose.yml start app
```

> The volume name is prefixed with the compose project name
> (`lab-app-db_pgdata`). Confirm yours with `docker volume ls`.

## Restore procedure (step by step)

```bash
# 0. Stop everything that writes to the volume.
docker compose -f compose/app-db/docker-compose.yml down

# 1. Restore into the (now empty or stale) volume.
docker run --rm \
  -v lab-app-db_pgdata:/data \
  -v "$BACKUP_DIR":/backup:ro \
  alpine sh -c 'rm -rf /data/* /data/..?* /data/.[!.]* ; tar xzf /backup/pgdata-2026-10-20-0900.tar.gz -C /data'

# 2. Fix ownership if the DB complains (postgres:16-alpine expects uid 70).
docker run --rm -v lab-app-db_pgdata:/data alpine chown -R 70:70 /data

# 3. Start the stack and check the DB answers.
docker compose -f compose/app-db/docker-compose.yml up -d
docker compose -f compose/app-db/docker-compose.yml exec db pg_isready
```

## Backup discipline (the part people skip)

- **Test the restore.** An untested backup is a rumor. Restore to a scratch
  volume (`docker volume create pgdata-test`) quarterly and `pg_isready` it.
- **Keep a copy off the host.** The tarball next to the volume protects
  against `docker volume rm` accidents, not against losing the host.
- **Name backups with timestamps**, keep N recent ones, prune the rest.
- **Document the RTO/RPO** for each volume: how long a restore takes, and how
  much data loss the business accepts. If nobody can answer, that's the real
  finding.
