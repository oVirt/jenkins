#!/bin/bash -xe
source automation/stdci_minishift.sh
source automation/stdci_venv.sh

main() {
    minishift::setup
    stdci_venv::activate "$0"
    python -m pytest -vv \
        --junitxml='exported-artifacts/minishift_fixture.junit.xml' \
        systest/test_minishift_fixture.py
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
