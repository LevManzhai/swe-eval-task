#!/usr/bin/env bash
# Full self-check for the task. Builds the environment image once, then runs
# the hidden verifier against the starting state, the reference solution, every
# alternative solution and every wrong solution, and prints one PASS/FAIL line
# per expectation. Exits non-zero if any expectation is violated.
#
#   ./run.sh              build the image, then run the whole matrix
#   SKIP_BUILD=1 ./run.sh reuse an image that was already built
#   DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=mirror/python:3.12.16-bookworm" ./run.sh
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="${IMAGE_TAG:-markdown-it-task:selfcheck}"
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

    docker run --rm --network none --memory 2g "${mounts[@]}" "$IMAGE_TAG" \
        bash -c "$setup && $command" 2>&1 | tail -n 4
    return "${PIPESTATUS[0]}"
}

HIDDEN="cd /workspace/verifier && python -m pytest test_task.py -q -p no:cacheprovider -W ignore::DeprecationWarning"
# The upstream suite (tests/test_packaging builds an sdist with flit_core,
# which works offline).
UPSTREAM="cd /workspace/repo && timeout 900 python -m pytest -q -p no:cacheprovider tests"

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
