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
    remove_packages || failed=true
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

remove_packages() {
    # Remove packages if they are installed
    local package_list=(python2-paramiko)
    local tool

    if [[ -e '/usr/bin/dnf' ]]; then
        # Fedora-specific packages
        package_list+=()
        if can_sudo dnf; then
            tool='dnf'
        fi
    else
        # CentOS-specific packages
        package_list+=()
        if can_sudo yum; then
            tool='yum'
        fi
    fi
    if [[ -z "$tool" ]]; then
        log WARN "Skipping removal of packages. No permissions."
        return
    fi
    local failed=0
    for package in "${package_list[@]}"; do
        if ! "$tool" list --disablerepo='*' "$package"; then
            log INFO "Skipping $package: not installed"
            continue
        fi
        log INFO "Removing $package"
        if ! sudo -n "$tool" remove -y "$package"; then
            log WARN "Could not remove $package"
            failed=1
        fi
    done
    return $failed
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
    # packages common for all distros
    local package_list=(
        git mock sed bash procps-ng createrepo python-paramiko
        PyYAML python2-pyxdg python-jinja2 python-py
    )
    if [[ -e '/usr/bin/dnf' ]]; then
        # Fedora-specific packages
        package_list+=(python3-PyYAML python3-py python3-pyxdg)
        if can_sudo dnf; then
            package_list+=(firewalld haveged libvirt qemu-kvm nosync libselinux-utils)
        fi
    else
        # CentOS-specific packages
        package_list+=(python34-PyYAML)
        if can_sudo yum; then
            package_list+=(firewalld haveged libvirt qemu-kvm-rhev nosync libselinux-utils)
        fi
    fi
    verify_packages "${package_list[@]}"
}

docker_setup () {
    #Install docker engine and start the service
    log INFO "Trying to setup Docker"
    verify_packages docker || return 1
    log INFO "Trying to setup Docker python API"
    if ! verify_packages python2-docker python3-docker; then
        # We failed to install the new API version, try to install the old one
        log WARN "Failed to install new docker API (that is ok)."
        log INFO "Trying to install old docker API"
        if ! verify_packages python-docker-py; then
            log ERROR "Failed to install docker API."
            return 1
        fi
    fi
    log INFO "Starting docker service"
    if ! sudo -n systemctl start docker; then
        log ERROR "Failed to start docker service"
        return 1
    fi
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
        rpm -q --quiet --whatprovides "$package" && continue
        log ERROR "package '$package' is not, and could not be, installed"
        (( ++failed ))
    done
    return $failed
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
        prefix="global_setup[${FUNCNAME[1]}]"
    else
        prefix="global_setup"
    fi
    echo "$prefix $level: $message"
}

main "@$"
