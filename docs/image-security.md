# Image security

Four practices, in the order attackers actually exploit their absence.

## 1. No secrets in images -- ever

A secret baked into a layer is **forever**: it survives in layer history,
in registries, in every host that pulled the image, and in `docker history`.
`ENV DB_PASSWORD=hunter2` in a Dockerfile is a credential leak with extra steps.

Do this instead:

| Secret type | Right place |
|---|---|
| Runtime config (DB password, API keys) | `.env` file (gitignored) + compose `env_file:` -- see both stacks |
| Build-time secret (private pip index token) | `RUN --mount=type=secret,id=pip_token pip install ...` -- never lands in a layer |
| TLS certs, htpasswd files | Mounted at runtime (`:ro`), never `COPY`'d |

Supporting hygiene: a `.dockerignore` that excludes `.env`, `*.pem`,
`.git/`, and local data dirs, so a stray `COPY . .` can't sweep secrets in.
(This repo's Dockerfiles `COPY` only the files they need -- same effect,
stronger guarantee.)

## 2. Least-privilege users

Containers run as **root by default**. A container breakout or a file-write
vuln as root is a host-compromise short step away.

- `USER appuser` in the python-app Dockerfile: created with nologin shell,
  owns only `/app`.
- The nginx image uses the vendor's **unprivileged variant**, which already
  runs as `nginx` on port 8080 -- don't hand-roll what the vendor hardened.
- Even the toolbox image (`alpine-utils`) runs as non-root `netop`. Habit
  beats exceptions.

Interview-ready line: *"I treat USER as mandatory, not hardening -- root in
a container should require a written justification."*

## 3. Pinned base tags

`python:3.12-slim-bookworm`, not `python:latest`. Why:

- **Reproducibility:** `latest` moves; two builds a week apart can ship
  different OpenSSL versions, and then you're debugging a ghost.
- **Blast radius:** a compromised or broken upstream `latest` auto-flows
  into your next build. Pinned tags make upgrades a deliberate `git diff`.
- Next step up: **pin the digest** (`FROM python:3.12-slim-bookworm@sha256:…`)
  so even a tag re-push can't change what's inside. Tags are mutable;
  digests aren't.

Tradeoff, stated honestly: pinning means *you* own upgrades. Put base-image
bumps on a cadence (monthly is sane for a small shop) and read the changelog
before bumping majors.

## 4. Minimal bases

| Base | Size | When |
|---|---|---|
| `alpine` (~7 MB) | tiny | Toolboxes, Go/Rust static binaries, nginx |
| `*-slim` (~50 MB) | small | Python/Node apps (this repo's app) |
| full distro | large | You need the toolchain *in* prod -- rare; justify it |
| distroless | tiny | Hardened prod services; debugging is harder (no shell) |

Smaller base = fewer packages = fewer CVEs to triage on scan day. Note the
musl caveat: alpine uses musl libc, and some Python wheels assume glibc --
if `pip install` breaks on alpine, `*-slim-bookworm` (glibc) is the pragmatic
fallback, which is exactly why this repo's app uses slim, not alpine.

## The loop that keeps images safe

1. **Scan** on a schedule: `docker scout` or Trivy against every image you ship.
2. **Rebuild** regularly -- base images get CVE fixes; a 6-month-old image is
   a 6-month-old patch level no matter how clean the Dockerfile is.
3. **Keep Dockerfiles boring:** pinned, minimal, non-root, secret-free. Every
   clever trick in a Dockerfile is a future incident.
