# Starting environment for the "tomlkit out-of-order tables" task.
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

# tomlkit at a pinned commit, with the toml-test suite its tests depend on.
ARG TOMLKIT_COMMIT=7bf7284dbd622557d9909f8fee017a4cb169a139
RUN git clone https://github.com/python-poetry/tomlkit.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$TOMLKIT_COMMIT" \
    && git submodule update --init --depth 1

# Bring the repository to the starting state, then drop its git history so the
# solver cannot read the upstream commits that fixed these bugs.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && rm -rf .git tests/toml-test/.git .gitmodules /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state"

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo

WORKDIR /workspace/repo
