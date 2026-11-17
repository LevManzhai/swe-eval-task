#!/usr/bin/env bash
# Full self-check for the task. Builds the environment image once, then runs
# the hidden verifier against the starting state, the reference solution, every
# alternative solution and every wrong solution, and prints one PASS/FAIL line
# per expectation. Exits non-zero if any expectation is violated.
#
# Every solution is a directory holding werkzeug.patch and flask.patch, applied
# to /workspace/werkzeug and /workspace/flask.
#
#   ./run.sh              build the image, then run the whole matrix
#   SKIP_BUILD=1 ./run.sh reuse an image that was already built
#   DOCKER_BUILD_ARGS="--build-arg BASE_IMAGE=mirror/python:3.12.16-bookworm" ./run.sh
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="${IMAGE_TAG:-flask-rare-task:selfcheck}"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

# Run a command in a fresh container with networking disabled, after applying
# the solution in directory $1 (empty for the starting state).
run_in_container() {
    local solution_dir="$1"
    local command="$2"
    local mounts=(-v "$SCRIPT_DIR/verifier/test_task.py:/workspace/verifier/test_task.py:ro")
    local setup="true"

    if [ -n "$solution_dir" ]; then
        for name in werkzeug flask; do
            if [ -s "$solution_dir/$name.patch" ]; then
                mounts+=(-v "$solution_dir/$name.patch:/workspace/$name.patch:ro")
                setup="$setup && git -C /workspace/$name apply /workspace/$name.patch"
            fi
        done
    fi

    docker run --rm --network none "${mounts[@]}" "$IMAGE_TAG" \
        bash -c "$setup && $command" 2>&1 | tail -n 4
    return "${PIPESTATUS[0]}"
}

HIDDEN="cd /workspace/verifier && python -m pytest test_task.py -q -p no:cacheprovider"
UPSTREAM="cd /workspace/werkzeug && python -m pytest -q -p no:cacheprovider tests && cd /workspace/flask && python -m pytest -q -p no:cacheprovider tests"

expect() {
    local expected="$1" label="$2" solution_dir="$3" command="$4"
    echo "--- $label"
    run_in_container "$solution_dir" "$command"
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
expect pass "starting state passes the upstream test suites" "" "$UPSTREAM"
expect fail "starting state fails the hidden verifier" "" "$HIDDEN"

echo "=== Correct solutions"
for dir in "$SCRIPT_DIR"/solution/reference "$SCRIPT_DIR"/verifier/alt_fixes/*/; do
    dir="${dir%/}"
    name="$(basename "$dir")"
    expect pass "$name passes the upstream test suites" "$dir" "$UPSTREAM"
    expect pass "$name passes the hidden verifier" "$dir" "$HIDDEN"
done

echo "=== Wrong solutions"
for dir in "$SCRIPT_DIR"/verifier/wrong_fixes/*/; do
    dir="${dir%/}"
    name="$(basename "$dir")"
    # The visible suites must not give the wrong solutions away
    expect pass "$name passes the upstream test suites" "$dir" "$UPSTREAM"
    expect fail "$name fails the hidden verifier" "$dir" "$HIDDEN"
done

echo
if [ $FAILED -eq 0 ]; then
    echo "ALL EXPECTATIONS MET"
else
    echo "SOME EXPECTATIONS WERE VIOLATED"
fi
exit $FAILED
