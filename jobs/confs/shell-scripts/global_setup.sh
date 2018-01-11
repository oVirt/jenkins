#!/bin/bash -xe
echo "shell-scripts/global_setup.sh"
#
# Executes all the commands that must be run on any job
#
shopt -s nullglob

main() {
    local failed=false

    setup_os_repos
    mk_wokspace_dirs
    extra_packages || failed=true

    if can_sudo systemctl; then
        docker_setup || failed=true
        setup_postfix || failed=true
    else
        log WARN "Skipping services setup - not enough sudo permissions"
    fi

    # If we failed in any step, abort to avoid breaking the host
    if $failed; then
        log ERROR "Aborting."
        return 1
    fi
    return 0
}

setup_os_repos() {
    local os
    local arch
    local conf_file

    if ! can_sudo cp; then
        log WARN "Skipping slave repo setup - no sudo permissions"
    fi
    if [[ ! -e /etc/os-release ]]; then
        log INFO "Cannot find '/etc/os-release', Skipping slave repo config".
        return
    fi
    source /etc/os-release
    os="${ID:?}${VERSION_ID:?}"
    arch="$(uname -i)"
    log DEBUG "Detected slave OS: $os"
    log DEBUG "Detected slave arch: $arch"
    if [[ $arch == x86_64 ]]; then
        conf_file="$WORKSPACE/jenkins/data/slave-repos/${os}.conf"
    else
        conf_file="$WORKSPACE/jenkins/data/slave-repos/${os}-${arch}.conf"
    fi
    if [[ ! -e "$conf_file" ]]; then
        log INFO "File: '$conf_file' not found. Skipping slave OS repo config".
        return
    fi
    log INFO "Configuring slave repos with: '$conf_file'"
    for yum_conf in /etc{{/yum,}/yum.conf,/dnf/dnf.conf}; do
        [[ -f "$yum_conf" ]] || continue
        if cmp --quiet "$yum_conf" "$conf_file"; then
            log INFO: "'$yum_conf' does not need to be updated"
            continue
        fi
        log INFO: "Placing repo configuration in: '$yum_conf'"
        sudo -n cp --backup --suffix=.rbk "$conf_file" "$yum_conf"
        sudo -n restorecon "$yum_conf"
    done
}

mk_wokspace_dirs() {
    rm -rf "$WORKSPACE/tmp"
    mkdir -p "$WORKSPACE/"{tmp,exported-artifacts}
}

extra_packages() {
    # Add extra packages we need for mock_runner.sh
    if [[ -e '/usr/bin/dnf' ]]; then
        verify_packages python3-PyYAML PyYAML python3-pyxdg python2-pyxdg \
            python-jinja2 python-paramiko createrepo python-py python3-py mock
    else
        verify_packages python34-PyYAML PyYAML python2-pyxdg python-jinja2 \
            python2-paramiko createrepo qemu-kvm-ev libvirt python-py \
            python3-py mock
    fi
}

docker_setup () {
    #Install docker engine and start the service
    verify_packages docker
    if ! sudo -n systemctl start docker; then
        log ERROR "Failed to start docker.service"
        return 1
    fi
    log INFO "Docker service started"
    return 0
}

setup_postfix() {
    verify_packages postfix
    sudo -n systemctl enable postfix
    sudo -n systemctl start postfix
}

verify_packages() {
    local packages=("$@")

    local tool='/usr/bin/dnf'
    local tool_inst_opts=(--best --allowerasing)
    if [[ ! -e "$tool" ]]; then
        tool=/bin/yum
        tool_inst_opts=()
    fi
    if can_sudo "$tool"; then
        sudo -n "$tool" "${tool_inst_opts[@]}" install -y "${packages[@]}"
    fi
    local failed=0
    for package in "${packages[@]}"; do
        "$tool" provides --disablerepo='*' "$package" >& /dev/null && continue
        log ERROR "package '$package' is not, and could not be, installed"
        (( ++failed ))
    done
    return $failed
}

can_sudo() {
    local cmd

    for cmd in "$@"; do
        sudo -nl "$cmd" >& /dev/null || return 1
    done
}

log() {
    local level="${1:?}"
    shift
    local message="$*"
    local prefix

    if [[ ${#FUNCNAME[@]} -gt 1 ]]; then
        prefix="global_setup[${FUNCNAME[1]}]"
    else
        prefix="global_setup"
    fi
    echo "$prefix $level: $message"
}

main "@$"
