# Starting environment for the "urllib3 response edge cases" task.
#
# Base image, upstream commit and every Python package are pinned (hypercorn
# is urllib3's own fork, at a fixed commit, as upstream's test setup uses).
# Network is only needed while building the image; the task and the verifier
# run offline. The full (non-slim) Python image already ships git.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# urllib3 at a pinned commit (14 November 2026).
ARG URLLIB3_COMMIT=d9f9b0ad5b99247e06aa9a50b7a5747aa5c2e35d
RUN git clone https://github.com/urllib3/urllib3.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$URLLIB3_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. Markdown files
# at the repository root other than the README are contributor guidance and
# are removed.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' ! -name README.md -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

# The version normally comes from git tags, which are gone.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=2.7.0.dev0
RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo \
    && python -c "import urllib3; assert urllib3.__file__.startswith('/workspace/repo'), urllib3.__file__"

WORKDIR /workspace/repo
