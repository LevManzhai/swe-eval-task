# Pinned exact patch version so the base image is fully reproducible.
FROM python:3.9.18-slim-bookworm

# Build-only dependency, not present in the final layer's relevant state
# (git is only needed to materialize /workspace/repo at the pinned commit).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Clone the real upstream library and reset to the exact parent commit that
# predates the fix. This is the starting state the solver works from.
RUN git clone https://github.com/pallets/flask.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard 5239458f28c5e3057f9987ceb2e6d33b9d9532d3

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# Make the checked-out library importable without a separate "pip install -e"
# step (the real repo has no compiled extensions, so this is sufficient).
ENV PYTHONPATH=/workspace/repo

WORKDIR /workspace
