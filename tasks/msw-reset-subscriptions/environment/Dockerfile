# Starting environment for the "msw subscriptions after resetHandlers()" task.
#
# Base image, upstream commit, pnpm and every dependency (through the
# repository's pnpm-lock.yaml) are pinned. Network is only needed while
# building the image; the task and the verifier run offline.
ARG BASE_IMAGE=node:22.21.1-bookworm
FROM ${BASE_IMAGE}

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    CI=1

# pnpm version from the repository's "packageManager" field, cached by
# corepack so that it works without network later.
RUN corepack enable && corepack prepare pnpm@11.27.1 --activate

WORKDIR /workspace

# msw at a pinned commit (9 October 2026).
ARG MSW_COMMIT=3818a81
RUN git clone https://github.com/mswjs/msw.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$MSW_COMMIT"

# Bring the repository to the starting state, then drop its git history so
# the solver cannot read the upstream commit that fixed this. Markdown files
# at the repository root other than the README and the license (changelog,
# contributor guidance) are removed.
COPY starting_state.patch /workspace/starting_state.patch
RUN cd /workspace/repo \
    && git apply /workspace/starting_state.patch \
    && find . -maxdepth 1 -name '*.md' ! -name README.md ! -name LICENSE.md -delete \
    && rm -rf .git /workspace/starting_state.patch \
    && git init -q \
    && git -c user.name=task -c user.email=task@localhost add -A \
    && git -c user.name=task -c user.email=task@localhost commit -q --no-verify -m "starting state"

# Install the locked dependencies and build once. The Node.js tests import
# msw from the built "lib/" directory, so every test run rebuilds first.
RUN cd /workspace/repo \
    && pnpm install --frozen-lockfile --ignore-scripts \
    && pnpm build

WORKDIR /workspace/repo
