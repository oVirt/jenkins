#!/bin/bash -ex

# Run this script in order to enable your OC cluster for integration
# with K8S Jenkins plugin.

oc_process() {
    local in="${1:?}"
    local out="${2:?}"
    shift 2
    local extra_params

    [[ $# -gt 0 ]] && extra_params="$(printf -- '-v %s ' "$@")"

    oc process \
       $extra_params \
        -o yaml \
        -f "$in" \
        > "$out" \
        || die "Failed to render template"
}

die() {
    local msg="${1:-An error occurred}"
    local ret="${2:-1}"
    local red="\x1b[31m"
    local default="\x1b[0m"

    printf "%b%s%b\n" "$red" "$msg" "$default" >&2
    exit "$ret"
}

usage() {
    echo "
    Usage:
        $0 NAMESPACE JENKINS_SLAVE_SVC_ACC

    This script deploys the required manifests on Openshift in order to
    connect it to Jenkins (using K8S plugin).

    Positional arguments:
        NAMESPACE
            In which namespace the objects should be deployed

        JENKINS_SLAVE_SVC_ACC
            The name of the services account that will be used by the
            Jenkins pods.
"
}

main() {
    [[ ! ("$1" && "$2") ]] && usage && exit 1

    local template="${0%/*}/jenkins-kubernetes-plugin-template.yaml"
    local manifest="$(mktemp)"
    local pod_template="${0%/*}/pod-slave.yaml"
    local pod_manifest="$(mktemp)"
    local namespace="$1"
    local jenkins_slave_svc_acc="$2"

    _oc_process() {
        oc_process \
            "${1:?}" \
            "${2:?}" \
            "PROJECT_NAME=${namespace}" \
            "SLAVE_SVC_ACCOUNT=${jenkins_slave_svc_acc}"
    }

    oc whoami &> /dev/null \
    || die "Please login to an Openshift cluster before running this script"

    _oc_process "$template" "$manifest" || exit 1
    oc create -f "$manifest" || die "Failed to create manifest $manifest"

    oc adm policy add-scc-to-user privileged \
        -z "$jenkins_slave_svc_acc" \
        -n "$namespace" \
        || die "Failed to add SCC to the jenkins slave svc account"

    _oc_process "$pod_template" "$pod_manifest" || exit 1
    echo "Pod manifest can be found in $pod_manifest"
}


[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"
