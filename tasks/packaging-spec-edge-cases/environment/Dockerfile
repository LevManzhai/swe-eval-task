# Starting environment for the "packaging spec edge cases" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
# The full (non-slim) Python image already ships git.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

# pytest depends on packaging, so a released copy of packaging gets installed
# here. The editable install of the repository below replaces it, so the only
# importable `packaging` is the one under test (pip's own vendored copy is an
# old release and is left alone).
COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# packaging at a pinned commit (17 November 2026).
ARG PACKAGING_COMMIT=6a69a83d8d89c6a01d554a8ad1b420cbb45fb4bc
RUN git clone https://github.com/pypa/packaging.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$PACKAGING_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. Markdown files
# at the repository root are contributor guidance and are removed.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo \
    && python -c "import packaging, sys; assert packaging.__file__.startswith('/workspace/repo'), packaging.__file__"

WORKDIR /workspace/repo
