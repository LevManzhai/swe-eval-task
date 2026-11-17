# Starting environment for the "Flask and Werkzeug rare inputs" task.
#
# Base image, both upstream commits and every Python package are pinned.
# Network is only needed while building the image; the task and the verifier
# run offline. The full (non-slim) Python image already ships git.
ARG BASE_IMAGE=python:3.12.16-bookworm
FROM ${BASE_IMAGE}

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# Werkzeug at a pinned commit of 9 November 2026, Flask of 30 October 2026.
ARG WERKZEUG_COMMIT=0f43c6ebd426039e4b99ec22535c2c8a2ec2f69f
ARG FLASK_COMMIT=49943b5a94413a530761350f04e896f76e8d620e
RUN git clone https://github.com/pallets/werkzeug.git /workspace/werkzeug \
    && git -C /workspace/werkzeug reset --hard "$WERKZEUG_COMMIT" \
    && git clone https://github.com/pallets/flask.git /workspace/flask \
    && git -C /workspace/flask reset --hard "$FLASK_COMMIT"

# Bring both repositories to the starting state, then drop their git history
# so the solver cannot read the upstream commits that fixed these bugs. The
# markdown files at each repository root other than the README are
# contributor and contributor-tool guidance, and are removed too.
COPY werkzeug_starting_state.patch flask_starting_state.patch /workspace/
RUN for name in werkzeug flask; do \
        cd /workspace/$name \
        && git apply /workspace/${name}_starting_state.patch \
        && find . -maxdepth 1 -name '*.md' ! -name README.md -delete \
        && rm -rf .git /workspace/${name}_starting_state.patch \
        && git init -q \
        && git -c user.name=task -c user.email=task@localhost add -A \
        && git -c user.name=task -c user.email=task@localhost commit -q -m "starting state" \
        || exit 1; \
    done

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/werkzeug -e /workspace/flask

WORKDIR /workspace
