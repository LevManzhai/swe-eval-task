# Starting environment for the "redis-py connection lifecycle" task.
#
# Base image, Redis server, upstream commit and every Python package are
# pinned. Network is only needed while building the image; the task and the
# verifier run offline, against a Redis server started inside the container.
#
# The full (non-slim) Python image already ships git, so nothing is installed
# with apt. BASE_IMAGE can point at a registry mirror of the same image.
ARG BASE_IMAGE=python:3.12.16-bookworm
ARG REDIS_IMAGE=redis:7.4.12-bookworm
FROM ${REDIS_IMAGE} AS redis
FROM ${BASE_IMAGE}

# The Redis server binaries, from the official image built on the same Debian
COPY --from=redis /usr/local/bin/redis-server /usr/local/bin/redis-cli /usr/local/bin/

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# redis-py at a pinned commit (16 November 2026).
ARG REDIS_PY_COMMIT=09c5cbfbfe593b5e4527a002acb94ffdaeed4ded
RUN git clone https://github.com/redis/redis-py.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$REDIS_PY_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. The markdown
# files at the repository root other than the README are contributor and
# contributor-tool guidance, not part of the library, and are removed too.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' ! -name README.md -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps -e /workspace/repo

# Start a Redis server for the tests: `redis-server --daemonize yes` (port 6379).
WORKDIR /workspace/repo
