# Starting environment for the "anyio cancellation safety" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
# Only the asyncio backend is installed: trio and uvloop are left out on
# purpose (see NOTES.md).
#
# The full (non-slim) image already ships git, so nothing is installed with
# apt. BASE_IMAGE can point at a registry mirror of the same image.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# anyio at a pinned commit (16 November 2026).
ARG ANYIO_COMMIT=9df02f0b8362e9f4a1fc3a4404052d0d7016e4f0
RUN git clone https://github.com/agronholm/anyio.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$ANYIO_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. The markdown
# files at the repository root are contributor-tool guidance, not part of the
# library, and are removed as well.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && rm -rf .git ./*.md /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

# anyio's version comes from git tags, which are gone after the step above.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=4.16.1.dev0
RUN pip install --no-cache-dir --no-deps -e /workspace/repo

WORKDIR /workspace/repo
