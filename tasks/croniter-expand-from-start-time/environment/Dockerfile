# Starting environment for the "croniter expand_from_start_time" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
FROM python:3.12.16-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

ARG CRONITER_COMMIT=ddb3495cf4eb1e7b0cc33b6baa0e9c4f36fb0c60
RUN git clone https://github.com/pallets-eco/croniter.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$CRONITER_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that implemented this behaviour.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo

WORKDIR /workspace/repo
