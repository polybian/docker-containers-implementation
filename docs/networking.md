# Networking: bridge vs host, and port mapping (LAB)

## The two modes you will actually use

### Bridge (the default -- use this)

Every compose stack in this repo runs on a **user-defined bridge network**
(`appnet`, `monnet`). Each container gets its own network namespace and a
private IP; Docker runs an embedded DNS server so containers resolve each
other **by service name** (`db:5432`, `app:8000`, `prometheus:9090`). That is
why the app connects to `db`, not to an IP -- IPs change on every recreate,
names don't.

- **Isolation:** containers can't see the host's network or each other across
  networks unless you connect them.
- **Port mapping** (`ports:`) is how you selectively punch a hole:
  `"127.0.0.1:8000:8000"` means host port 8000 -> container port 8000, and
  the `127.0.0.1:` prefix means **only the loopback interface**. Without the
  IP prefix, Docker binds `0.0.0.0` -- reachable from the whole LAN, which is
  how "internal" dashboards end up on Shodan.

### Host (the exception -- know why before you use it)

`network_mode: host` removes the namespace: the container shares the host's
network stack directly. No port mapping needed (and `ports:` is ignored).

Legit uses: a monitoring agent that must sniff host interfaces, or squeezing
out the last bit of latency on a high-throughput box. Costs: **zero network
isolation** (a compromised container sees host traffic), port conflicts with
host services, and it doesn't work the same on Docker Desktop (Mac/Windows).

## When each fits an IT shop

| Situation | Pick |
|---|---|
| App + DB stack, internal services | User-defined bridge (this repo's default) |
| You need the service from your laptop only | Bridge + `127.0.0.1:` port mapping |
| Service must be LAN-reachable (e.g. intranet wiki) | Bridge + explicit host IP/port mapping, firewall in front |
| Host-level network agent (packet capture, NetFlow) | Host mode, documented and justified |
| "Just make it work" with no isolation thinking | Never a reason -- that's how breaches happen |

## Rules of thumb

1. **Bind to loopback first.** `"127.0.0.1:8000:8000"` in compose; widen only
   deliberately. `docker ps` shows you exactly what got published -- check it.
2. **Let the app bind `0.0.0.0` *inside* the container.** The container's
   namespace is already isolated; access control happens at the `ports:` layer.
   (See `docker/python-app/app.py`.)
3. **DBs don't get `ports:`** unless a human needs direct access *right now* --
   and then it's loopback-only, temporarily. The app-db stack's Postgres has
   no published port; you reach it via `docker compose exec db psql ...`.
4. **One network per concern.** `appnet` and `monnet` are separate; the
   monitoring stack reaches the app only through the documented
   `docker network connect` step (see `compose/monitoring/prometheus.yml`).
   Blast radius stays small.
