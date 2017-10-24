#!/bin/bash -xe
echo "shell-scripts/global_setup.sh"
#
# Executes all the commands that must be run on any job
#
shopt -s nullglob

main() {
    local failed=false

    setup_os_repos
    mk_wokspace_tmp
    extra_packages || failed=true
    docker_setup || failed=true
    setup_postfix || failed=true

    # If we failed in any step, abort to avoid breaking the host
    if $failed; then
        echo "Aborting."
        return 1
    fi
    return 0
}

setup_os_repos() {
    local os
    local arch
    local conf_file

    if [[ ! -e /etc/os-release ]]; then
        echo "Cannot find '/etc/os-release'"
        echo "Skipping slave OS repo configuration".
        return
    fi
    source /etc/os-release
    os="${ID:?}${VERSION_ID:?}"
    arch="$(uname -i)"
    echo "Detected slave OS: $os"
    echo "Detected slave arch: $arch"
    if [[ $arch == x86_64 ]]; then
        conf_file="$WORKSPACE/jenkins/data/slave-repos/${os}.conf"
    else
        conf_file="$WORKSPACE/jenkins/data/slave-repos/${os}-${arch}.conf"
    fi
    if [[ ! -e "$conf_file" ]]; then
        echo "Configuration file: '$conf_file' not found."
        echo "Skipping slave OS repo configuration".
        return
    fi
    echo "Configuring slave repos with: '$conf_file'"
    for yum_conf in /etc{{/yum,}/yum.conf,/dnf/dnf.conf}; do
        [[ -f "$yum_conf" ]] || continue
        if cmp --quiet "$yum_conf" "$conf_file"; then
            echo "'$yum_conf' does not need to be updated"
            continue
        fi
        echo "Placing repo configuration in: '$yum_conf'"
        sudo cp --backup --suffix=.rbk "$conf_file" "$yum_conf"
        sudo restorecon "$yum_conf"
    done
}

mk_wokspace_tmp() {
    rm -rf "$WORKSPACE/tmp"
    mkdir -p "$WORKSPACE/tmp"
}

extra_packages() {
    # Add extra packages we need for mock_runner.sh
    if [[ -e '/usr/bin/dnf' ]]; then
        sudo dnf -y install python3-PyYAML PyYAML python3-pyxdg pyxdg \
            python-jinja2 python-paramiko
    else
        sudo yum -y install python34-PyYAML PyYAML pyxdg \
            python-jinja2 python2-paramiko
    fi
}

docker_setup () {
    #Install docker engine and start the service
    sudo yum -y install docker
    if ! sudo systemctl start docker; then
        echo "[DOCKER SETUP] Failed to start docker.service"
        return 1
    fi
    echo "[DOCKER SETUP] Docker service started"
    return 0
}

setup_postfix() {
    if [[ -e '/usr/bin/dnf' ]]; then
        sudo dnf -y install postfix
    else
        sudo yum -y install postfix
    fi
    sudo systemctl enable postfix
    sudo systemctl start postfix
}

main "@$"
