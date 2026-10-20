# syntax=docker/dockerfile:1
# LAB: tiny alpine network-diagnostics toolbox for the IT shop.
# Demonstrates: minimal base image, single install layer, non-root user.
# Usage: docker run --rm -it lab-utils dig example.com
#        docker run --rm lab-utils curl -s http://app:8000/health

# Practice: MINIMAL BASE + PINNED TAG. Alpine is ~7 MB and ships almost
# nothing -- the opposite of a "kitchen sink" Ubuntu image. Pinning 3.21
# avoids the day `alpine:latest` moves and your dig flags change behavior.
FROM alpine:3.21

# Practice: ONE RUN LAYER for installs, with --no-cache so the apk index
# never lands in a layer (smaller image, no stale index). Tools are
# deliberately unpinned: for a diagnostics toolbox, "latest dig" beats
# reproducible-but-ancient dig. The tradeoff is documented in
# docs/image-security.md, and the linter exception below is intentional.
# hadolint ignore=DL3018
RUN apk add --no-cache \
        bind-tools \
        curl \
        iproute2 \
        iputils \
        jq \
        netcat-openbsd \
    && adduser -D -s /bin/sh netop
# bind-tools=dig/nslookup  curl=HTTP/API pokes  iproute2=ip addr/route
# iputils=ping  jq=JSON log wrangling  netcat-openbsd=quick TCP probes

# Practice: NON-ROOT EVEN FOR A TOOLBOX. Habit beats exceptions -- a
# diagnostics container with root is one `docker run -v /:/host` away from
# a very bad day.
USER netop
WORKDIR /home/netop

# Default to a shell; override per-run, e.g. `docker run --rm lab-utils ping -c3 app`.
CMD ["/bin/sh"]
