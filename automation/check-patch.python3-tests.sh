#!/bin/bash -xe

PYTHON_3_TESTS_DIR=test3

main() {
    if ! command -v python3; then
        echo "ERROR: Could not find python3"
        return 1
    fi
    setup_pipenv
    pipenv sync --dev
    run_tests
}

setup_pipenv() {
    PATH="/usr/local/bin:$PATH"
    python3 -m pip --cache-dir="$PIPENV_CACHE_DIR" install pipenv
}

run_tests() {
    pipenv run py.test \
        -vvv \
        --junitxml="exported-artifacts/pipenv-pytest.junit.xml" \
        "${PYTHON_3_TESTS_DIR}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
