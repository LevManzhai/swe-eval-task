#!/bin/bash
# The hidden tests are upstream's tests for these fixes, taken from the
# upstream test files at the base commit (with the wording of warnings and of
# new error messages left ungraded). They run inside the repository's tests/
# directory so that tests/conftest.py provides their fixtures.
set -e
cp /workspace/verifier/hidden/*.py /workspace/repo/tests/
cd /workspace/repo
mapfile -t IDS < /workspace/verifier/hidden_tests.txt
exec python -m pytest -q -p no:cacheprovider "${IDS[@]}"
