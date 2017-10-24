#!/bin/bash -e
echo "shell-scripts/project_setup.sh"
#
# Setup project specific requirements
#

main(){
    local failed=false

    filter_secret_data || failed=true

    # If we failed in any step, abort to avoid breaking the host
    if $failed; then
        echo "Aborting."
        return 1
    fi
    return 0
}

filter_secret_data() {
    # Filter secret data by project and version (vars injected via JJB)
    local failed=0
    if ! [[ -f "${CI_SECRETS_FILE}" && -v STD_VERSION && -v PROJECT ]]; then
        # Dont fail if secrets_file doesn't exist,
        # or if STD_VERSION or PROJECT are not set
        return 0
    fi
    python "$WORKSPACE"/jenkins/scripts/secrets_resolvers.py \
        -f "${CI_SECRETS_FILE}" \
        filter "${PROJECT}" "${STD_VERSION}" > \
        "$WORKSPACE"/std_ci_secrets.yaml || failed=1
    rm -f "${CI_SECRETS_FILE}" || failed=1
    return $failed
}

main "@$"
