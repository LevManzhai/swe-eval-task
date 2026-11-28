# Starting environment for the "mistune edge cases" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
# The full (non-slim) Python image already ships git.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /workspace/requirements.txt

# mistune at a pinned commit (24 October 2026).
ARG MISTUNE_COMMIT=f7ec702edfc1ad5579a76f881238841af266d93c
RUN git clone https://github.com/lepture/mistune.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$MISTUNE_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. Markdown files
# at the repository root other than the README are contributor and
# contributor-tool guidance and are removed.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' ! -name README.md -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo \
    && python -c "import mistune; assert mistune.__file__.startswith('/workspace/repo'), mistune.__file__" \
    && test -z "$(find / -path /proc -prune -o -type d -name mistune -print 2>/dev/null | grep -v '^/workspace/repo')"

WORKDIR /workspace/repo
