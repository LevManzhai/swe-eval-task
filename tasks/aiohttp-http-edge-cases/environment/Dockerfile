# Starting environment for the "aiohttp HTTP edge cases" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
#
# aiohttp is installed from source without its C extensions, so the
# pure-Python HTTP parser and helpers are the ones in use. The full (non-slim)
# Python image already ships git, so nothing is installed with apt.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# aiohttp at a pinned commit (16 November 2026). The llhttp submodule is not
# needed: the C parser is not built.
ARG AIOHTTP_COMMIT=b2350c3d330608165c9b51c3d291a5123c4364b9
RUN git clone https://github.com/aio-libs/aiohttp.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$AIOHTTP_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. The markdown
# files at the repository root are contributor and contributor-tool guidance,
# not part of the library, and are removed too.
COPY starting_state.patch /workspace/starting_state.patch
ENV AIOHTTP_NO_EXTENSIONS=1
# Installed while the clone has no .git directory, because the build script
# insists on the llhttp submodule in a git checkout, and the C parser it is for
# is not built anyway.
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo \
    && pip install --no-cache-dir --no-deps pytest-aiohttp==1.1.1 pytest-asyncio==1.5.0 \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

WORKDIR /workspace/repo
