#!/bin/bash -xe

source automation/stdci_venv.sh

PYTHON_3_TESTS_DIR=test3

main() {
    if ! command -v python3; then
        echo "ERROR: Could not find python3"
        return 1
    fi
    stdci_venv::activate "$0"
    run_tests
}

run_tests() {
    python3 -m pytest -vvv "${PYTHON_3_TESTS_DIR}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
