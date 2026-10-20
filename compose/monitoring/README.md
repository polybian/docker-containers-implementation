# monitoring stack (LAB)

Prometheus + Grafana on their own bridge network (`monnet`).

## Run it (on a Docker host)

```bash
cp .env.example .env      # then fill in GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD
docker compose up -d
# Prometheus UI: http://127.0.0.1:9090   Grafana: http://127.0.0.1:3000
```

## Design notes

- **Scrape config is a real file** (`prometheus.yml`), mounted `:ro`. It
  scrapes Prometheus itself plus the `lab-app` target from the app-db stack
  at `/metrics` -- see the comments in `prometheus.yml` for the one
  cross-stack networking step that requires.
- **Grafana is a placeholder with honest defaults**: pinned image, named
  volume for dashboards, sign-ups disabled, admin creds from `.env`.
  Wiring the Prometheus datasource in Grafana (Add data source -> Prometheus
  -> URL `http://prometheus:9090`) is the intended next exercise.
- Both UIs bind **loopback-only** -- monitoring dashboards should never be
  LAN-reachable without auth in front; see `docs/networking.md`.
