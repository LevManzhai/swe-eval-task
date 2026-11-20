# Starting environment for the "dateutil time zone edge cases" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
# The full (non-slim) Python image already ships git and the system time zone
# database.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

# --no-deps: freezegun would otherwise pull in a released python-dateutil,
# which already contains the fixes this task is about.
COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /workspace/requirements.txt

# dateutil at a pinned commit (17 November 2026).
ARG DATEUTIL_COMMIT=261e2913961865300032cf30df1d59f4f0ff6f1a
RUN git clone https://github.com/dateutil/dateutil.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$DATEUTIL_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. Markdown files
# at the repository root other than the README and AUTHORS.md (which the build
# needs) are contributor and contributor-tool guidance and are removed.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' ! -name README.md ! -name AUTHORS.md -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo \
    && python -c "import dateutil; assert dateutil.__file__.startswith('/workspace/repo'), dateutil.__file__" \
    && test -z "$(find / -path /proc -prune -o -type d -name dateutil -print 2>/dev/null | grep -v '^/workspace/repo')"

WORKDIR /workspace/repo
