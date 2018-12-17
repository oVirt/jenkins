#!/bin/bash -xe
source automation/stdci_venv.sh

main() {
    stdci_venv::activate "$0"
    python -m pytest -vv \
        --junitxml='exported-artifacts/playbooks.junit.xml' \
        playbooks
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
