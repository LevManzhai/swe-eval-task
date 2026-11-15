#!/usr/bin/env bash
# Full self-check for the task. Builds the environment image once, then
# re-runs the hidden verifier against the starting state, the reference
# fix, every alt fix, and every wrong fix, printing a clear PASS/FAIL line
# for each expectation. Exits non-zero if any expectation is violated.
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="flask-blueprint-slash-task:selfcheck"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

# Run the verifier inside a container built from the task image, with an
# optional patch applied first. Networking is disabled for the test run,
# matching how the verifier is graded. Returns pytest's exit code.
run_verifier() {
    local patch_file="$1"
    local container_name="flask-slash-task-run-$$"

    if [ -n "$patch_file" ]; then
        docker run --rm --network none \
            --name "$container_name" \
            -v "$SCRIPT_DIR/verifier/test_task.py:/workspace/test_task.py:ro" \
            -v "$patch_file:/workspace/fix.patch:ro" \
            "$IMAGE_TAG" \
            bash -c "cd /workspace/repo && git apply /workspace/fix.patch && cd /workspace && python -m pytest test_task.py -q" \
            > /tmp/run_verifier_output.$$ 2>&1
    else
        docker run --rm --network none \
            --name "$container_name" \
            -v "$SCRIPT_DIR/verifier/test_task.py:/workspace/test_task.py:ro" \
            "$IMAGE_TAG" \
            bash -c "cd /workspace && python -m pytest test_task.py -q" \
            > /tmp/run_verifier_output.$$ 2>&1
    fi
    local rc=$?
    cat /tmp/run_verifier_output.$$
    rm -f /tmp/run_verifier_output.$$
    return $rc
}

echo "=================================================================="
echo "Step (a): build the image"
echo "=================================================================="
if docker build -t "$IMAGE_TAG" -f "$SCRIPT_DIR/environment/Dockerfile" "$SCRIPT_DIR/environment" > /tmp/build_output.$$ 2>&1; then
    pass "image builds"
else
    cat /tmp/build_output.$$
    fail "image builds"
fi
rm -f /tmp/build_output.$$

echo
echo "=================================================================="
echo "Step (b): starting state must FAIL the verifier"
echo "=================================================================="
run_verifier ""
if [ $? -ne 0 ]; then
    pass "starting state fails verifier (bug is present)"
else
    fail "starting state fails verifier (verifier unexpectedly passed on buggy code)"
fi

echo
echo "=================================================================="
echo "Step (c): reference.patch must PASS the verifier"
echo "=================================================================="
run_verifier "$SCRIPT_DIR/solution/reference.patch"
if [ $? -eq 0 ]; then
    pass "reference.patch passes verifier"
else
    fail "reference.patch passes verifier"
fi

echo
echo "=================================================================="
echo "Step (d): each alt_fixes/ patch must PASS the verifier"
echo "=================================================================="
for p in "$SCRIPT_DIR"/verifier/alt_fixes/*.patch; do
    name="$(basename "$p")"
    echo "--- alt fix: $name ---"
    run_verifier "$p"
    if [ $? -eq 0 ]; then
        pass "alt_fixes/$name passes verifier"
    else
        fail "alt_fixes/$name passes verifier"
    fi
done

echo
echo "=================================================================="
echo "Step (e): each wrong_fixes/ patch must FAIL the verifier"
echo "=================================================================="
for p in "$SCRIPT_DIR"/verifier/wrong_fixes/*.patch; do
    name="$(basename "$p")"
    echo "--- wrong fix: $name ---"
    run_verifier "$p"
    if [ $? -ne 0 ]; then
        pass "wrong_fixes/$name fails verifier"
    else
        fail "wrong_fixes/$name fails verifier"
    fi
done

echo
echo "=================================================================="
if [ "$FAILED" -eq 0 ]; then
    echo "OVERALL: PASS - all expectations met"
    exit 0
else
    echo "OVERALL: FAIL - one or more expectations were not met"
    exit 1
fi
