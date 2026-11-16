#!/usr/bin/env bash
# Full self-check for the task. Builds the environment image once, then runs
# the hidden verifier against the starting state, the reference solution, every
# alternative solution and every wrong solution, and prints one PASS/FAIL line
# per expectation. Exits non-zero if any expectation is violated.
#
#   ./run.sh              build the image, then run the whole matrix
#   SKIP_BUILD=1 ./run.sh reuse an image that was already built
#   DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=mirror/python:3.12.16-bookworm --build-arg REDIS_IMAGE=mirror/redis:7.4.12-bookworm" ./run.sh
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="${IMAGE_TAG:-redis-lifecycle-task:selfcheck}"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

# Run a command inside a fresh container, optionally after applying a patch to
# the repository. Networking is disabled, exactly as when the task is graded.
# Prints the tail of the output and returns the command's exit code.
run_in_container() {
    local patch_file="$1"
    local command="$2"
    local mounts=(-v "$SCRIPT_DIR/verifier/test_task.py:/workspace/verifier/test_task.py:ro")
    local setup="true"

    if [ -n "$patch_file" ]; then
        mounts+=(-v "$patch_file:/workspace/candidate.patch:ro")
        setup="git -C /workspace/repo apply /workspace/candidate.patch"
    fi

    docker run --rm --network none "${mounts[@]}" "$IMAGE_TAG" \
        bash -c "$setup && $command" 2>&1 | tail -n 4
    return "${PIPESTATUS[0]}"
}

# Both commands start a Redis server inside the container first.
START_REDIS="redis-server --daemonize yes --enable-debug-command yes >/dev/null && sleep 0.5"
HIDDEN="$START_REDIS && cd /workspace/verifier && python -m pytest test_task.py -q -p no:cacheprovider -o asyncio_mode=auto"
# The upstream tests for the code this task touches (standalone server only),
# minus one test that expects Redis 8 behaviour from the 7.4 server.
UPSTREAM="$START_REDIS && cd /workspace/repo && python -m pytest -q -p no:cacheprovider -o addopts= -o log_cli=false -m 'not onlycluster and not redismod and not ssl and not replica and not cp_integration' -k 'not test_subscriber_mode_rejects_regular_command_after_ssubscribe' tests/test_asyncio/test_connection_pool.py tests/test_asyncio/test_pubsub.py tests/test_asyncio/test_pipeline.py tests/test_asyncio/test_monitor.py tests/test_asyncio/test_usage_counter.py tests/test_asyncio/test_connection.py tests/test_connection_pool.py tests/test_pubsub.py tests/test_pipeline.py tests/test_monitor.py tests/test_connection.py"

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
