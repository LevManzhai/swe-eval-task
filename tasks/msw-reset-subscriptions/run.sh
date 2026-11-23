#!/usr/bin/env bash
# Full self-check for the task. Builds the environment image once, then runs
# the hidden verifier against the starting state, the reference solution, every
# alternative solution and every wrong solution, and prints one PASS/FAIL line
# per expectation. Exits non-zero if any expectation is violated.
#
#   ./run.sh              build the image, then run the whole matrix
#   SKIP_BUILD=1 ./run.sh reuse an image that was already built
#   DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=mirror.gcr.io/library/node:22.21.1-bookworm" ./run.sh
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="${IMAGE_TAG:-msw-task:selfcheck}"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

# Run a command inside a fresh container, optionally after applying a patch to
# the repository. Networking is disabled, exactly as when the task is graded.
# Prints the tail of the output and returns the command's exit code.
run_in_container() {
    local patch_file="$1"
    local command="$2"
    local mounts=(-v "$SCRIPT_DIR/verifier/task.node.test.ts:/workspace/verifier/task.node.test.ts:ro")
    local setup="true"

    if [ -n "$patch_file" ]; then
        mounts+=(-v "$patch_file:/workspace/candidate.patch:ro")
        setup="git -C /workspace/repo apply /workspace/candidate.patch"
    fi

    docker run --rm --network none "${mounts[@]}" "$IMAGE_TAG" \
        bash -c "$setup && $command" 2>&1 | tail -n 4
    return "${PIPESTATUS[0]}"
}

# The hidden tests are copied into the repository's own Node.js test tree so
# they run with its Vitest configuration. msw's Node.js tests import the built
# "lib/" directory, so the candidate is built first.
HIDDEN="pnpm build >/dev/null && cp /workspace/verifier/task.node.test.ts test/msw-api/setup-server/task-verifier.node.test.ts && pnpm vitest run --project=node test/msw-api/setup-server/task-verifier.node.test.ts"
# The repository's unit and Node.js test projects. The browser projects need
# Playwright browsers, which the image does not ship. Four files are left out
# because they need something the offline container doesn't have: three Node.js
# scenarios resolve a public host name (test.mswjs.io), and the Vite plugin
# test launches Chromium. They are deleted inside the throwaway container.
OFFLINE_INCOMPATIBLE="src/vite/plugin.test.ts \
  test/msw-api/setup-server/scenarios/fall-through.node.test.ts \
  test/msw-api/setup-server/scenarios/on-unhandled-request/callback.node.test.ts \
  test/msw-api/setup-server/scenarios/on-unhandled-request/default.node.test.ts"
UPSTREAM="rm -f $OFFLINE_INCOMPATIBLE && pnpm build >/dev/null && pnpm vitest run --project=unit --project=node"

expect() {
    local expected="$1" label="$2" patch_file="$3" command="$4"
    echo "--- $label"
    run_in_container "$patch_file" "$command"
    local rc=$?
    if [ "$expected" = "pass" ] && [ $rc -eq 0 ]; then
        pass "$label"
    elif [ "$expected" = "fail" ] && [ $rc -ne 0 ]; then
        pass "$label"
    else
        fail "$label (exit code $rc, expected to $expected)"
    fi
}

if [ "${SKIP_BUILD:-0}" != "1" ]; then
    echo "=== Building $IMAGE_TAG"
    docker build ${DOCKER_BUILD_ARGS:-} -t "$IMAGE_TAG" "$SCRIPT_DIR/environment" || { echo "FAIL: image build"; exit 1; }
fi

echo "=== Starting state"
expect pass "starting state passes the upstream test suite" "" "$UPSTREAM"
expect fail "starting state fails the hidden verifier" "" "$HIDDEN"

echo "=== Correct solutions"
for patch in "$SCRIPT_DIR"/solution/reference.patch "$SCRIPT_DIR"/verifier/alt_fixes/*.patch; do
    name="$(basename "$patch")"
    expect pass "$name passes the upstream test suite" "$patch" "$UPSTREAM"
    expect pass "$name passes the hidden verifier" "$patch" "$HIDDEN"
done

echo "=== Wrong solutions"
for patch in "$SCRIPT_DIR"/verifier/wrong_fixes/*.patch; do
    name="$(basename "$patch")"
    # The visible suite must not give the wrong solutions away
    expect pass "$name passes the upstream test suite" "$patch" "$UPSTREAM"
    expect fail "$name fails the hidden verifier" "$patch" "$HIDDEN"
done

echo
if [ $FAILED -eq 0 ]; then
    echo "ALL EXPECTATIONS MET"
else
    echo "SOME EXPECTATIONS WERE VIOLATED"
fi
exit $FAILED
