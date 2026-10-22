# Docker Containers Implementation — Docker for IT Operations

A hands-on implementation for running containers the way a small IT shop should:
hardened images, compose stacks with sane networking, named-volume backups,
a real troubleshooting runbook, and a log-triage helper with tests.

**What this demonstrates:** multi-stage Docker builds, least-privilege
containers (non-root users, unprivileged nginx), HEALTHCHECK design,
bridge networking and loopback-only port publishing, secrets-at-runtime
(no credentials in images), named-volume backup/restore procedure,
Prometheus scraping config, and testable Python tooling (stdlib only).

**Scope:** everything here is demo-grade by design -- placeholder secrets,
loopback-only publishing, no real data. Nothing in this repo is production
configuration; the patterns transfer, the values don't.

```
  ┌───────────────────────── app-db stack ─────────────────────────┐
  │  ┌──────────┐   appnet (bridge, internal)   ┌──────────────┐    │
  │  │ demo-app  │ ──────────────────────────▶  │   demo-db     │    │
  │  │ (python) │        db:5432 (Docker DNS)  │ (postgres 16)│    │
  │  └────┬─────┘      no published port        └──────┬───────┘    │
  │       │ :8000 → 127.0.0.1:8000 (loopback only)     │ pgdata      │
  └───────┼────────────────────────────────────────────┼─────────────┘
          │              monnet (bridge)               │ named volume
  ┌───────┼──────────── monitoring stack ─────────────┼─────────────┐
  │       │     ┌──────────────┐  scrape /metrics  ┌──▼───────────┐ │
  │       ├──▶  │  prometheus  │ ◀───────────────── │  demo-app     │ │
  │       │     │    :9090     │  (network connect │  (app-db)    │ │
  │       ├──▶  │   grafana    │   documented in   └──────────────┘ │
  │             │    :3000     │   prometheus.yml)                  │
  │             └──────────────┘  promdata + grafanadata (volumes)  │
  └───────────────────────────────────────────────────────────────┘
```

## Repo layout

| Path | Purpose |
|---|---|
| `docker/python-app/` | Multi-stage Python service (`app.py` + `Dockerfile`): pinned tag, non-root user, stdlib HEALTHCHECK, `/health` + `/metrics` endpoints |
| `docker/nginx-proxy/` | Hardened reverse proxy: vendor **unprivileged** nginx variant, pinned tag, custom `nginx.conf` (`server_tokens off`, `/healthz`) |
| `docker/alpine-utils/` | Tiny alpine network-diagnostics toolbox (`dig`, `curl`, `ip`, `ping`, `jq`, `nc`) as non-root |
| `compose/app-db/` | Stack 1: app + Postgres on internal bridge network, named volume, split `.env.app`/`.env.db` per service, loopback-only publishing |
| `compose/monitoring/` | Stack 2: Prometheus (real `prometheus.yml` scrape config) + Grafana placeholder, named volumes |
| `scripts/collect-logs.py` | Log triage helper (stdlib only): `--dir` or `--container` mode, error counts, top error lines, text report |
| `tests/test_collect_logs.py` | 16 unit tests for the log collector |
| `docs/architecture.md` | Design decisions: why multi-stage, why non-root, stack layout rationale |
| `docs/networking.md` | Bridge vs host networking, port mapping, when each fits an IT shop |
| `docs/volumes-backup.md` | Volumes vs bind mounts; step-by-step named-volume backup/restore |
| `docs/troubleshooting.md` | Runbook: crashing containers, failed pulls, port conflicts, disk pressure |
| `docs/image-security.md` | No secrets in images, least privilege, pinned tags, minimal bases |

## Quick start

**Without Docker** (everything below ran locally):

```bash
# Run the app directly -- stdlib only, no build needed
python3 docker/python-app/app.py &
curl http://127.0.0.1:8000/health     # {"status": "ok", ...}
curl http://127.0.0.1:8000/metrics    # Prometheus exposition format

# Triage some logs
python3 scripts/collect-logs.py --dir /path/to/logs --top 10
python3 scripts/collect-logs.py --dir /path/to/logs --output report.txt

# Run the tests
python3 -m unittest discover -s tests -v
```

**On a Docker host** (needs the docker CLI -- not available locally):

```bash
# Stack 1: app + db
cp compose/app-db/.env.app.example compose/app-db/.env.app
cp compose/app-db/.env.db.example compose/app-db/.env.db   # fill in secrets first
docker compose -f compose/app-db/docker-compose.yml up -d --build
curl http://127.0.0.1:8000/health

# Stack 2: monitoring
cp compose/monitoring/.env.example compose/monitoring/.env
docker compose -f compose/monitoring/docker-compose.yml up -d
# Prometheus: http://127.0.0.1:9090   Grafana: http://127.0.0.1:3000

# Build the standalone images
docker build -t demo-app ./docker/python-app
docker build -t demo-nginx ./docker/nginx-proxy
docker build -t demo-utils ./docker/alpine-utils
```

## Security notes

- **No secrets in images, ever.** All `.env.*.example` files contain only
  `<generate-your-own>` placeholders; real `.env` files are gitignored. Config
  arrives at runtime via compose `env_file`, never baked into a layer.
  Env files are split per service (`.env.app` vs `.env.db`) so the app never
  receives `POSTGRES_PASSWORD`.
- **Non-root everywhere:** `appuser`, the unprivileged nginx variant's
  `nginx` user, and `netop` in the toolbox.
- **Loopback-only publishing** (`127.0.0.1:` prefix) on every published port;
  the database has **no** published port at all.
- **Pinned base tags** on all images (`python:3.12-slim-bookworm`,
  `nginxinc/nginx-unprivileged:1.27.4-alpine`, `alpine:3.21`,
  `postgres:16-alpine`, `prom/prometheus:v2.55.1`, `grafana/grafana:11.4.0`).
- Full treatment in `docs/image-security.md`; networking posture in
  `docs/networking.md`.

## Validation

### Ran locally (real results)

**Unit tests -- 16/16 passing:**

```
$ python3 -m unittest discover -s tests -v
test_failed_docker_logs_raises (test_collect_logs.TestDockerMode.test_failed_docker_logs_raises) ... ok
test_missing_docker_cli_raises (test_collect_logs.TestDockerMode.test_missing_docker_cli_raises) ... ok
test_successful_docker_logs (test_collect_logs.TestDockerMode.test_successful_docker_logs) ... ok
test_container_mode_without_docker_exits_1 (test_collect_logs.TestMain.test_container_mode_without_docker_exits_1) ... ok
test_dir_mode_writes_report (test_collect_logs.TestMain.test_dir_mode_writes_report) ... ok
test_missing_dir_exits_2 (test_collect_logs.TestMain.test_missing_dir_exits_2) ... ok
test_mutually_exclusive_sources (test_collect_logs.TestMain.test_mutually_exclusive_sources) ... ok
test_empty_dir (test_collect_logs.TestReadEntries.test_empty_dir) ... ok
test_reads_only_dot_log (test_collect_logs.TestReadEntries.test_reads_only_dot_log) ... ok
test_counts (test_collect_logs.TestSummarize.test_counts) ... ok
test_empty_entries (test_collect_logs.TestSummarize.test_empty_entries) ... ok
test_error_regex_word_boundaries (test_collect_logs.TestSummarize.test_error_regex_word_boundaries) ... ok
test_per_file_breakdown (test_collect_logs.TestSummarize.test_per_file_breakdown) ... ok
test_report_sections (test_collect_logs.TestSummarize.test_report_sections) ... ok
test_time_range (test_collect_logs.TestSummarize.test_time_range) ... ok
test_top_errors_ranking (test_collect_logs.TestSummarize.test_top_errors_ranking) ... ok

Ran 16 tests in 0.012s -- OK
```

**Log collector -- real run against synthetic logs** (15 lines across 2 files
in `/tmp`, outside the repo):

```
$ python3 scripts/collect-logs.py --dir /tmp/demo-logs --top 5
LOG COLLECTION REPORT
Source       : directory /tmp/demo-logs (2 .log file(s))
Generated    : 2026-10-20 20:56:03 UTC

Total lines  : 15
Error lines  : 6 (40.0%)
Warning lines: 1
Time range   : 2026-10-20 08:00:00 -> 2026-10-20 08:05:00

Top 5 error lines (by frequency):
  2x  2026-10-20 08:01:11 FATAL password authentication failed for user "app"
  1x  2026-10-20 08:01:11 ERROR db connection refused: dial tcp 10.0.0.5:5432: connect: connection refused
  1x  2026-10-20 08:01:12 ERROR db connection refused: dial tcp 10.0.0.5:5432: connect: connection refused
  1x  2026-10-20 08:01:13 ERROR db connection refused: dial tcp 10.0.0.5:5432: connect: connection refused
  1x  2026-10-20 08:04:44 Traceback (most recent call last):

Per-file breakdown:
  app.log: 10 lines, 4 errors
  db.log: 5 lines, 2 errors
```

**The Python app -- real run** (started directly, no Docker):

```
$ python3 docker/python-app/app.py &
$ curl -s http://127.0.0.1:8000/health
{"status": "ok", "host": "htch-runtime", "requests": 1}
$ curl -s http://127.0.0.1:8000/metrics
# HELP demo_app_up 1 when the app is serving traffic
# TYPE demo_app_up gauge
demo_app_up 1
# HELP demo_app_requests_total Total HTTP requests served
# TYPE demo_app_requests_total counter
demo_app_requests_total 2
$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/nope
404
```

Request logging to stdout verified (what `docker logs` would capture):

```
127.0.0.1 - - [20/Oct/2026 20:56:01] "GET /health HTTP/1.1" 200 -
127.0.0.1 - - [20/Oct/2026 20:56:01] "GET /nope HTTP/1.1" 404 -
```

**YAML -- all 3 files parse:**

```
YAML OK: compose/app-db/docker-compose.yml
YAML OK: compose/monitoring/docker-compose.yml
YAML OK: compose/monitoring/prometheus.yml
```

**Dockerfiles -- hadolint 2.12.0** (downloaded for this check): all 3 clean.
One finding during the check (`DL3018` -- unpinned `apk` packages in
`alpine-utils`) was a deliberate, documented tradeoff for a diagnostics
toolbox; it now carries an explicit `# hadolint ignore=DL3018` with the
justification in the Dockerfile and in `docs/image-security.md`.

**Secret scan -- clean:** `grep` for credential patterns across the repo
found no real secrets. All `.env.*.example` files contain only
`<generate-your-own>` placeholders; remaining hits are docs discussing
secrets and the `.gitignore` itself. (`--container` mode fails cleanly here:
`error: docker CLI not found on PATH`, exit 1 -- also covered by tests.)

### Needs a real Docker host (not validated here)

- **Image builds** (`docker build` on all 3 Dockerfiles) -- no docker CLI
  available locally, so nothing was built. The Dockerfiles passed hadolint and
  the app code ran for real, but the actual `docker build` is unverified.
- **`docker compose up`** on both stacks, healthcheck behavior
  (`service_healthy` gating), and the cross-stack `docker network connect`
  step for Prometheus scraping `demo-app:8000`.
- **Volume backup/restore** commands in `docs/volumes-backup.md` -- the
  procedure is written step-by-step but was not executed (no daemon).
- **`nginx -t`** on `nginx.conf` -- syntax reviewed by hand, not validated
  against a real nginx binary.

### Honest limitations

- The collector's "top error lines" counts **exact** lines: two identical
  errors with different timestamps show as separate entries (visible in the
  run above). Timestamp-normalized grouping is a possible v2 improvement.
- Error detection is heuristic regex (`ERROR|FATAL|Traceback|...`), not a
  parser -- right for triage, wrong for alerting.
- `prometheus.yml` targets `demo-app:8000`, which only resolves after the
  documented cross-stack network step; until then Prometheus shows the
  target DOWN (the config comments say so).
