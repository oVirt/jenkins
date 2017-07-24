#!/bin/bash -xe
echo "shell-scripts/global_setup_apply.sh"
#
# Apply configurations from global_setup.sh that can be rolled back
# This script is to be run only upon job success
#
main() {
    apply_os_repos
}

apply_os_repos() {
    for yum_conf in /etc{{/yum,}/yum.conf,/dnf/dnf.conf}; do
        [[ -f "$yum_conf" ]] || continue
        [[ -f "${yum_conf}.rbk" ]] || continue
        echo "Applying OS repo update for: $yum_conf"
        sudo mv --force "${yum_conf}.rbk" "${yum_conf}.old"
    done
}

main "@$"
