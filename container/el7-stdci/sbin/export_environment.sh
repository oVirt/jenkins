#!/bin/bash -xe

# An array of variables to be exported to /etc/stdci_env
INCLUDE_LIST=(
    HOSTNAME JENKINS_URL JENKINS_SECRET STDCI_SLAVE_CONTAINER_NAME
    JENKINS_AGENT_NAME CI_RUNTIME_UID CI_RUNTIME_UNAME JENKINS_AGENT_WORKDIR
    CONTAINER_SLOTS container
)

main() {
    local export_path="${1:?}"
    local include

    include=$(join "${INCLUDE_LIST[@]}")
    /usr/bin/tr \\000 \\n < /proc/1/environ |
        grep -E "^($include)=" >> "$export_path"
    chmod 0644 "$export_path"
}

join() {
    local IFS="|"
    echo "$*"
}

main "$@"
