#!/bin/bash -xe
echo "shell-scripts/global_setup_apply.sh"
#
# Apply configurations from global_setup.sh that can be rolled back
# This script is to be run only upon job success
#
main() {
    apply_os_repos
    apply_known_hosts
}

apply_os_repos() {
    for yum_conf in /etc{{/yum,}/yum.conf,/dnf/dnf.conf}; do
        [[ -f "$yum_conf" ]] || continue
        [[ -f "${yum_conf}.rbk" ]] || continue
        echo "Applying OS repo update for: $yum_conf"
        sudo -n mv --force "${yum_conf}.rbk" "${yum_conf}.old"
    done
}

apply_known_hosts() {
    local known_hosts="$HOME/.ssh/known_hosts"
    apply_file "$known_hosts"
}

apply_file() {
    local file="${1:?}"
    local rbk_file="${file}.rbk"
    local old_file="${file}.old"

    [[ -f "$file" ]] && [[ -f "$rbk_file" ]] || return 0
    echo "Keeping configuration file $file"
    sudo -n mv --force "$rbk_file" "$old_file"
}

main "@$"
