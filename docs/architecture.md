# Architecture & design decisions

## Why multi-stage builds

The python-app Dockerfile has a **builder** stage and a **runtime** stage.
The builder verifies the app (`py_compile` smoke check); the runtime stage
copies forward *only the verified artifact*. Nothing from the build
environment -- no compilers, no caches, no check tooling -- ships in the
final image. With real dependencies the payoff is bigger: `pip install`
happens in the builder, and only the installed packages (not pip, not the
wheel cache) land in production. Smaller image, smaller attack surface, and
a build that fails *at build time* instead of at 3am.

## Why non-root everywhere

All three images run as unprivileged users (`appuser`, `nginx`, `netop`).
Container isolation is good but not perfect; a file-write vulnerability or
a container-escape bug as root is a host compromise, as a non-root user it's
a contained incident. The nginx image goes one step further by using the
vendor's **unprivileged variant** rather than a hand-rolled `USER` drop --
upstream already solved the "bind port 80 needs root" problem by listening
on 8080, so we adopt their solution instead of inventing our own.

## Why HEALTHCHECKs that need no extra tools

Both service images define `HEALTHCHECK`s built from what's already in the
image: the Python app probes `/health` with stdlib `urllib` (slim images
ship no curl), nginx probes `/healthz` with busybox `wget` (already in
alpine). Healthchecks are what make `depends_on: condition: service_healthy`
meaningful -- without them, compose only waits for the container to *start*,
and "started" is not "ready". That's the classic race where the app boots
faster than Postgres and crashes on the first query.

## Stack layout rationale

**Two stacks, not one.** `app-db` is the workload; `monitoring` is the
observer. Separate compose projects = separate networks (`appnet`,
`monnet`), separate lifecycles, separate blast radii. You can tear down and
rebuild monitoring without touching the database. The cost -- one explicit
`docker network connect` for cross-stack scraping -- is documented in
`compose/monitoring/prometheus.yml` and is itself a useful lesson in how
Docker DNS and network attachment work.

**The database is not published.** No `ports:` on `db` means Postgres exists
only inside `appnet`. External access goes through `docker compose exec`,
which is authenticated by host access, not by a network listener. Combined
with loopback-only publishing for the app (`127.0.0.1:8000:8000`), the
default posture is: *nothing in these stacks is reachable from the LAN
unless you deliberately widen it* (see `docs/networking.md`).

**Named volumes for all state** (`pgdata`, `promdata`, `grafanadata`):
`docker compose down` doesn't delete data, and the backup/restore runbook in
`docs/volumes-backup.md` targets named volumes specifically. Config the
operator edits (prometheus.yml) is a read-only bind mount instead -- config
and data have different lifecycles and should use different mechanisms.

## The log collector's place in this

`scripts/collect-logs.py` is the operational glue: containers log to
stdout/stderr (never to files inside the image -- that's why
`PYTHONUNBUFFERED=1` is set), and the script triages those streams into a
report (totals, error rate, top repeating errors, per-source breakdown).
It has two modes because reality has two modes: `--dir` for exported logs
and forensics on a box without Docker, `--container` for live triage via
`docker logs`. Pure functions (`summarize`, `format_report`) are separated
from I/O (`read_entries`, `docker_log_text`) so the logic is unit-testable
without a Docker host -- 16 tests prove it.

## Deliberately left out

- **No orchestrator** (Swarm/Kubernetes): compose is the right complexity
  for a small IT shop; the concepts (healthchecks, networks, volumes,
  secrets-at-runtime) transfer directly.
- **No TLS termination in this implementation**: nginx is configured as a reverse proxy
  with the security headers that matter (`server_tokens off`, dotfile deny);
  real TLS would terminate here with certs mounted `:ro` at runtime -- never
  baked into the image (see `docs/image-security.md`).
- **Grafana is provisioned but not wired**: adding the Prometheus datasource
  (`http://prometheus:9090`) is left as the reader's exercise, because
  clicking through it teaches more than reading about it.
