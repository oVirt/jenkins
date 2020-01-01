#!/bin/bash -xe
# run_oc_playbook.sh - STDCI script for running playbooks that interact with
#                      OpenShift
#
# This script requires the following environment variables to be defined:
#   - PLAYBOOK   - The name of the playbook to run (without path and extension)
#   - INVENTORY  - The name of the intentory to use (without path and extension)
#   - PB_ARGS    - Extra arguments (space separated) to pass to ansible-playbook
#   - APISERVER  - The URL of the OpenShift API server to connect to
#   - PROJECT    - The OpenShift project to use
#   - TOKEN      - The token to use for connecting to OpenShift
#   - OC_VERSION - (Optional) The version of the `oc` command to use
#
source scripts/safe_download.sh
source automation/stdci_venv.sh

PLAYBOOK="${PLAYBOOK:?}"
INVENTORY="${INVENTORY:?}"
APISERVER="${APISERVER:?}"
PROJECT="${PROJECT:?}"
TOKEN="${TOKEN:?}"
OC_VERSION="${OC_VERSION:-v3.11.0-0cbc58b}"

main() {
    setup
    run_oc_playbook "$@"
}

run_oc_playbook() {
    local playbook="playbooks/${PLAYBOOK}.yaml"
    local inventory="playbooks/inventories/${INVENTORY}.yaml"
    local pb_args

    # shellcheck disable=SC2153
    read -a pb_args <<<"$PB_ARGS"
    ansible-playbook "$playbook" -i "$inventory" -v "${pb_args[@]}" "$@"
}

setup() {
    skip_proxy_for_apiserver
    get_oc_bin
    oc_login
    ansible_config
    stdci_venv::activate "$0"
}

skip_proxy_for_apiserver() {
    # Make sure we don't try to access OpenShift via a proxy
    # shellcheck disable=SC2154
    if [[ $http_proxy ]]; then
        if [[ $no_proxy ]]; then
            no_proxy="$no_proxy,"
        fi
        local apiserver
        apiserver="${APISERVER#*//}"
        apiserver="${apiserver%:*}"
        no_proxy="${no_proxy}${apiserver}"
        export no_proxy
    fi
}

get_oc_bin() {
    local dl_site=https://github.com/openshift/origin/releases/download
    local version_dir="${OC_VERSION%%-*}"
    local pkg_prefix=openshift-origin-client-tools
    local pkg_suffix=linux-64bit.tar.gz
    local dl_name="$pkg_prefix-$OC_VERSION-$pkg_suffix"
    local dl_url="$dl_site/$version_dir/$dl_name"

    if [[ $UID -eq 0 ]] && [[ -d /var/host_cache ]]; then
        export OC_BIN_HOME=/var/host_cache/stdci_oc_bin
    else
        OC_BIN_HOME="$(mktemp -d oc_bin_home.XXXXXX --tmpdir)"
        export OC_BIN_HOME
    fi
    mkdir -p "$OC_BIN_HOME"

    safe_download -d sha256 \
        -s CHECKSUM_FILE \
        -a extract_oc_bin \
        "$OC_BIN_HOME/package.lock" \
        "$dl_url" \
        "$OC_BIN_HOME/package.tgz"

    if [[ -x "$OC_BIN_HOME/oc" ]]; then
        [[ "$PATH" == "$OC_BIN_HOME" ]] ||
            [[ "$PATH" == "$OC_BIN_HOME":* ]] ||
            [[ "$PATH" == *:"$OC_BIN_HOME" ]] ||
            [[ "$PATH" == *:"$OC_BIN_HOME":* ]] ||
            PATH="$OC_BIN_HOME:$PATH"
    else
        return 1
    fi
}

extract_oc_bin() {
    echo "extracting oc"
    local package="${1:?}"
    mkdir -p "$OC_BIN_HOME"
    tar -xOzf "$package" '*/oc' > "$OC_BIN_HOME/oc"
    chmod +x "$OC_BIN_HOME/oc"
}

oc_login() {
    KUBECONFIG="$(mktemp kubeconfig.XXXXXX --tmpdir)"
    export KUBECONFIG
    (set +x; echo oc login >&2; oc login "$APISERVER" --token="$TOKEN")
}

ansible_config() {
     export ANSIBLE_STDOUT_CALLBACK=yaml
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
