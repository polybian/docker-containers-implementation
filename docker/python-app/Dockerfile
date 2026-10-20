# syntax=docker/dockerfile:1
# LAB: multi-stage build for a tiny Python service.
# Demonstrates: pinned base tags, multi-stage builds, non-root runtime user,
# layer-cache-friendly ordering, HEALTHCHECK without extra tooling.

# ---------- Stage 1: builder ---------------------------------------------
# Practice: MULTI-STAGE BUILDS. The builder image carries everything needed
# to *verify* the app, and none of it ships in the final image -- smaller
# download, smaller attack surface. A broken app fails the build here,
# not at 3am in production.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /src
COPY app.py .
# Smoke-check the source in the builder stage. This layer is discarded;
# only the verified file below is copied forward.
RUN python3 -m py_compile app.py

# ---------- Stage 2: runtime ----------------------------------------------
# Practice: PINNED BASE TAG. `python:3.12-slim-bookworm` pins the interpreter
# minor version and the distro. Never `python:latest` -- "latest" moves under
# you and makes incidents unreproducible. (Pinning the digest as well is the
# next step up; see docs/image-security.md.)
FROM python:3.12-slim-bookworm

# Practice: LEAST PRIVILEGE. Create a non-root user and run as them. A
# compromised app process then can't rewrite system files, install packages,
# or read other containers' mounts.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
# Practice: COPY ONLY WHAT YOU NEED from the builder stage, with ownership
# set at copy time (--chown) so no extra chown layer is needed.
COPY --from=builder --chown=appuser:appuser /src/app.py /app/app.py

# Practice: LAYER-CACHE ORDERING. With real dependencies you'd COPY
# requirements.txt and `pip install` BEFORE copying source, so code edits
# don't bust the expensive dependency layer. This app is stdlib-only, so
# there is deliberately no dependency layer to bust.
# Practice: NO SECRETS. Nothing here embeds credentials -- config arrives at
# *runtime* via environment (compose `env_file`), never baked into a layer.

USER appuser
EXPOSE 8000
ENV APP_PORT=8000 \
    PYTHONUNBUFFERED=1
# PYTHONUNBUFFERED=1 keeps logs streaming to `docker logs` instead of
# sitting in a buffer -- essential for the log collector in scripts/.

# Practice: HEALTHCHECK. Uses the stdlib (urllib), because slim images ship
# no curl/wget. The orchestrator marks the container unhealthy when /health
# stops answering, which is what `depends_on: condition: service_healthy`
# keys off in the app-db stack.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"

# Practice: exec-form CMD (JSON array) so the app is PID 1 and receives
# SIGTERM directly -- no shell wrapper swallowing signals.
CMD ["python3", "/app/app.py"]
