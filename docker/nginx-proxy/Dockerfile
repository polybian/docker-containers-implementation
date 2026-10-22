# syntax=docker/dockerfile:1
# Hardened nginx reverse proxy.
# Demonstrates: vendor unprivileged variant (non-root by default), pinned
# tag, minimal config surface, HEALTHCHECK, no secrets in the image.

# Practice: RUN AS NON-ROOT THE EASY WAY. Instead of hand-rolling privilege
# drops, use the vendor's *unprivileged* variant: it listens on 8080 (no
# root needed for ports >= 1024) and already runs as the `nginx` user.
# Practice: PINNED TAG. `1.27.4-alpine` pins nginx version + minimal base.
FROM nginxinc/nginx-unprivileged:1.27.4-alpine

# Remove the stock default site (it ships a welcome page and extra surface)
# and install our hardened config with the least-privilege location blocks.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/demo.conf

# Practice: HEALTHCHECK. busybox wget ships in alpine, so no extra package.
# Failing health checks is how the orchestrator knows to replace this
# container instead of serving 502s forever.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1

# The base image already defaults to USER nginx; restated explicitly so
# the runtime user is documented in the Dockerfile itself.
USER nginx
EXPOSE 8080

# No CMD: the base image's default starts nginx in the foreground (exec
# form), so it stays PID 1 and handles SIGTERM cleanly on `docker stop`.
# Practice: NO SECRETS -- this image carries zero credentials; TLS certs or
# basic-auth files would be mounted at runtime, never COPY'd in.
