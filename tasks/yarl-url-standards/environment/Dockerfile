# Starting environment for the "yarl URL standards" task.
#
# Base image, upstream commit and every Python package are pinned. Network is
# only needed while building the image; the task and the verifier run offline.
# The full (non-slim) Python image already ships git.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

# yarl is installed as pure Python: the URL parsing lives in Python anyway,
# and this keeps the task about one implementation of the quoting helpers.
ENV YARL_NO_EXTENSIONS=1

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /workspace/requirements.txt

# yarl at a pinned commit (18 November 2026).
ARG YARL_COMMIT=5350e374eb1735aa275af45f574661a1ebb80ec7
RUN git clone https://github.com/aio-libs/yarl.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$YARL_COMMIT"

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs. Markdown files
# at the repository root other than the README are contributor and
# contributor-tool guidance and are removed. tools/conformance holds the
# web-platform-tests URL corpus, an RFC 3986 oracle and a report of where yarl
# differs from both, which would hand the solver the answer, so it goes too.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' ! -name README.md -delete \
    && rm -rf tools/conformance \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo \
    && python -c "import yarl; assert yarl.__file__.startswith('/workspace/repo'), yarl.__file__" \
    && test -z "$(find / -path /proc -prune -o -type d -name yarl -print 2>/dev/null | grep -v '^/workspace/repo')"

WORKDIR /workspace/repo
