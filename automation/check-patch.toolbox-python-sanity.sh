#!/bin/bash -ex
# toolbox-python-sanity.sh - Ensure that all python scripts included in the
#                            ci_toolbox work
#
main() {
    shopt -s extglob nullglob

    # Needed for dockerfile-utils
    python3 -m pip install "dockerfile-parse==0.0.15"

    for script in /var/lib/ci_toolbox/*; do
        # Lousy hack because we were not smart enough to leave the *.py
        # extension on the python scripts...
        if head -1 "$script" | grep -q python; then
            "$script" --help
        fi
    done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
