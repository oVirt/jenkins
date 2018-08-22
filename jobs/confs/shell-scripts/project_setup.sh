#!/bin/bash -e
echo "shell-scripts/project_setup.sh"
#
# Setup project specific requirements
# and setup/clean stuff that has to run after STDCI was cloned
#

WORKSPACE="${WORKSPACE?}"

main(){
    local failed=false

    cleanup_docker || failed=true
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

cleanup_docker () {
    local whitelisted_repos=( ${CACHED_DOCKER_REPOS:-centos fedora} )

    if ! [[ -x /bin/docker ]]; then
        log WARN "Skipping Docker cleanup - Docker not installed"
        return 0
    fi
    if ! can_sudo docker; then
        log WARN "Skipping Docker cleanup - no sudo permissions to use it"
        return 0
    fi
    if ! can_sudo systemctl; then
        log WARN "Skipping Docker cleanup - no permissions to manage services"
        return 0
    fi

    sudo -n systemctl start docker || return 1
    sudo -n "${WORKSPACE}/jenkins/scripts/docker_cleanup.py" \
        --debug --whitelist "${whitelisted_repos[@]}" || return 1
    return 0
}

can_sudo() {
    local cmd

    for cmd in "$@"; do
        sudo -nl $cmd >& /dev/null || return 1
    done
}

log() {
    local level="${1:?}"
    shift
    local message="$*"
    local prefix

    if [[ ${#FUNCNAME[@]} -gt 1 ]]; then
        prefix="cleanup_slave[${FUNCNAME[1]}]"
    else
        prefix="cleanup_slave"
    fi
    echo "$prefix $level: $message"
}

main "@$"
