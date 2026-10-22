# Troubleshooting runbook

Triage order is deliberate: **observe first** (`ps`, `logs`, `inspect`),
**interact second** (`exec`), **destroy last** (recreate/prune). Never start
with `prune` -- see "Disk pressure" below.

## 1. Container won't start / keeps restarting

```bash
docker ps -a                          # STATUS column: Exited (1)? Restarting?
docker logs demo-app --tail 50         # the app's own last words -- start here
docker logs demo-app --tail 50 --timestamps   # correlate with events
docker inspect demo-app --format '{{.State.Error}} {{.State.ExitCode}}'
```

- **Exit 1 with a stack trace** -> application bug or bad config. Fix the
  code/env, `docker compose up -d --build`.
- **`Restarting (1) N seconds ago`** loop -> read the logs, then check
  `depends_on`: is it waiting on a DB whose healthcheck never passes?
  `docker compose ps` shows health status per service.
- **Exit 0 immediately** -> the main process daemonized or the CMD ended.
  Containers live only as long as PID 1. (Classic: `service nginx start`
  as CMD -- it forks and exits.)
- **Exit 137** -> OOM-killed (128 + SIGKILL 9). `docker inspect` ->
  `.State.OOMKilled: true`. Raise the memory limit or fix the leak.

## 2. Get a shell inside a running container

```bash
docker exec -it demo-app sh            # alpine/slim images: `sh`, not `bash`
docker exec demo-app ps aux            # non-interactive one-shot
docker exec -u root demo-app sh        # break-glass root, for diagnosis only
```

`exec` is for inspection, not for fixing: any change you make by hand dies
with the container. Fix the Dockerfile/compose file instead.

## 3. Image won't pull

```bash
docker pull postgres:16-alpine        # reproduce the pull by hand, read the error
```

- `unauthorized` / `denied` -> `docker login` (private registry) or the repo
  doesn't exist / is private.
- `not found` / `manifest unknown` -> **tag typo**. Tags are case-sensitive
  and exact; this is the #1 cause. Verify on the registry's tags page.
- `network timeout` / `i/o timeout` -> host DNS or egress proxy. Try
  `docker run --rm alpine nslookup registry-1.docker.io`; check `HTTP_PROXY`.
- Behind a corporate proxy, the *daemon* needs the proxy config, not just
  your shell -- that's a daemon.json / systemd drop-in fix.

## 4. Port conflicts

```
Error response from daemon: Ports are not available: exposing port TCP
0.0.0.0:8000 -> 0.0.0.0:0: listen tcp4 0.0.0.0:8000: bind: address already in use
```

```bash
docker ps --format '{{.Names}} {{.Ports}}'   # which container holds it?
ss -ltnp | grep 8000                          # or: is it a host process?
```

Fix: stop the squatter, or remap (`"127.0.0.1:8001:8000"`). Don't just keep
bumping ports -- find out *what* is listening; an unknown listener is a
finding, not an inconvenience.

## 5. Disk pressure from unused images

```bash
docker system df                              # where the GBs actually are
docker images --filter "dangling=true"         # untagged build leftovers
```

Prune **with care**, in this order -- each command prints what it will delete
and asks for confirmation:

```bash
docker image prune                 # dangling images only (safe)
docker image prune -a               # ALL unused images (re-pullable, but slow on bad links)
docker builder prune                # build cache (safe, just slower next build)
docker volume prune                 # UNRECOVERABLE DATA LOSS if a volume is detached --
                                    # never run this without checking `docker volume ls` first
```

Rules: never `docker system prune -a` on a host you don't fully understand;
never prune volumes in the same breath as images; on a shared/build host,
schedule pruning instead of doing it during an incident.

## 6. The 60-second triage (memorize this)

```bash
docker compose ps                   # which service is unhealthy?
docker logs <name> --tail 30        # what did it say last?
docker inspect <name> | grep -i -A2 health   # healthcheck output
docker exec <name> sh -c '<the failing thing by hand>'
```

If logs are silent, the process died before logging -> `inspect` the exit
code and OOM flag; if the healthcheck fails but the app works, `exec` in and
run the healthcheck command yourself -- usually a wrong port/path in the
HEALTHCHECK, not a dead app.
