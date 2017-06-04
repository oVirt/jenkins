#!/bin/bash -e
echo "shell-scripts/cleanup_slave.sh"

WORKSPACE="${WORKSPACE?}"
export PATH=$PATH:/usr/sbin

umount_everyhting_inside() {
    local mydir="${1?}"
    local res=0
    local inner_dirs=(
        $(mount | awk '{ print $3 }' | egrep "^$mydir" | sort -r)
    )
    local inner_dir
    for inner_dir in "${inner_dirs[@]}"; do
        sudo umount --lazy "$inner_dir" \
        && echo "    Umounted $inner_dir" \
        || {
            res=1
            echo "    FAILED to umount $inner_dir"
        }
    done
    return $res
}

safe_remove() {
    local dir="${1?}"
    [[ -e "$dir" ]] || return 0
    if [[ -d "$dir" ]]; then
        umount_everyhting_inside "$dir" \
        || return 1
        sudo rm -Rf "$dir"
    else
        sudo rm -f "$dir"
    fi
    return 0
}

cleanup_home() {
    local dir
    for dir in /home/*; do
        if ! grep -q "$dir" /etc/passwd; then
            echo "    Cleaning up non-user home dir $dir"
            safe_remove "$dir"
        fi
    done
}

cleanup_var() {
    local res=0
    local dir
    echo "Cleaning up /var/tmp"
    for dir in /var/tmp/*; do
        safe_remove "$dir" \
        || {
            echo "    Error cleaning up $dir, skipping"
            res=1
            continue
        }
    done
    echo "done"
    return $res
}

cleanup_postgres() {
    local db dbs
    echo "Cleaning up postgres databases"
    if ! [[ -e /var/lib/pgsql ]]; then
        echo "    Postgres installation not found, skipping"
        return 0
    fi
    pushd /tmp
    psql="sudo -u postgres psql"
    dbs=(
        $($psql -c "\l" \
          | grep engine \
          | cut -d '|' -f1)
    )
    for db in "${dbs[@]}"; do
        echo "    $db"
        $psql -c "DROP DATABASE $db;"
    done
    popd
    echo "done"
    return 0
}

cleanup_logs() {
    echo "Emptying some common logs"
    local log empty_logfiles remove_logfiles
    empty_logfiles=(
        /var/log/wtmp
    )
    remove_logfiles=(
        /var/log/messages-*
        /var/log/secure-*
    )
    for log in "${empty_logfiles[@]}"; do
        [[ -f "$log" ]] \
            && sudo bash -c "> $log" \
            && echo "    $log"
    done
    for log in "${remove_logfiles[@]}"; do
        [[ -f "$log" ]] \
            && safe_remove "$log" \
            && echo "    $log"
    done
    sudo dmesg -c >/dev/null
    echo "Done"
    return 0
}

cleanup_journal() {
    local dir
    echo "Cleaning up journal logs (if any)"
    if ! sudo service systemd-journald status &>/dev/null; then
        echo "  journald not running, skipping"
        return 0
    fi
    # Flush logs
    sudo systemctl kill --kill-who=main --signal=SIGUSR1 systemd-journald.service
    for dir in /var/log/journal/*; do
        safe_remove "$dir"
    done
    # force log reattach
    sudo service systemd-journald restart
}

cleanup_workspaces() {
    local cur_workspace="${1?}"
    local res=0
    local base_workspace workspace
    base_workspace=~jenkins/workspace
    echo "Cleaning up workspaces"
    for workspace in $base_workspace/*; do
        [[ -d "$workspace" ]] || continue
        [[ "$workspace" =~ ^$cur_workspace ]] && continue
        echo "    $workspace"
        safe_remove "$workspace" \
        || {
            echo "    Failed to remove $workspace, skipping"
            res=1
            continue
        }
    done
    return $res
}

cleanup_lago_network_interfaces() {
    local links \
        link
    local failed=false
    # remove lago-type interfaces, that is, 8chars of hash + '-some_tag'
    # or 4 chars of hash + 6 chars of hash
    links=(
        $( \
            sudo ip link show \
            | grep -Po '^[[:alnum:]]*: [[:alnum:]]{8}-[^:]*' \
            | awk '{print $2}' \
        )
        $( \
            sudo ip link show \
            | grep -Po '^[[:alnum:]]*: [[:alnum:]]{4}-[[:alnum:]]{6}[^:]*' \
            | awk '{print $2}' \
        )
    )
    for link in "${links[@]}"; do
        #If the interface has an '@' the name is before it
        link="${link%%@*}"
        echo "Removing interface $link"
        sudo ip link delete "$link" \
        || {
            failed=true
            echo "ERROR: Failed to cleanup interface $link"
        }
    done
    if $failed; then
        return 1
    fi
    return 0
}

cleanup_lago_vms() {
    local vm \
        vms
    local failed=false
    # remove lago-type vms, that is, 8chars of hash + '-some_tag'
    vms=($( \
        sudo virsh list \
        | grep -Po '^ *[[:digit:]]* +[[:alnum:]]{8}-[^[:space:]]*' \
        | awk '{print $2}' \
    ))
    for vm in "${vms[@]}"; do
        echo "Removing domain $vm"
        sudo virsh destroy "$vm" \
        || {
            failed=true
            echo "ERROR: Failed to cleanup domain $vm"
        }
    done
    if $failed; then
        return 1
    fi
    return 0
}

cleanup_lago_virtual_network_interfaces() {
    local links \
        link
    local failed=false
    # remove lago-type interfaces, that is, 8chars of hash + '-some_tag'
    links=($( \
        sudo virsh net-list \
        | grep -Po '^ *[[:alnum:]]{8}-[^[:space:]]*' \
    ))
    for link in "${links[@]}"; do
        echo "Removing virtual interface $link"
        sudo virsh net-destroy "$link" \
        || {
            failed=true
            echo "ERROR: Failed to cleanup virtual interface $link"
        }
    done
    if $failed; then
        return 1
    fi
    return 0
}

cleanup_loop_devices() {
    echo "Making sure there are no device mappings..."
    sudo dmsetup remove_all || :
    echo "Removing the used loop devices..."
    sudo losetup -D || :
    if [[ "$(sudo losetup)" != "" ]]; then
        echo "Failed to free all the loop devices:"
        sudo losetup
        echo "--- device mappings"
        sudo dmsetup info
        return 1
    fi
    return 0
}

cleanup_lago() {
    cleanup_lago_vms || :
    cleanup_lago_virtual_network_interfaces || :
    cleanup_lago_network_interfaces || :
    sudo service libvirtd restart || :
}

cleanup_libvirt() {
    # Drop all left over libvirt domains
    for UUID in $(sudo virsh list --all --uuid); do
        sudo -E virsh destroy $UUID || :
        sleep 2
        sudo -E virsh undefine --remove-all-storage --snapshots-metadata $UUID || :
    done
}

cleanup_docker () {
    # for now, we want to keep only centos and fedora official images
    local -r DOCKER_REPOS_WHITELIST="centos|fedora|"
    local fail=false

    if ! [[ -x /bin/docker ]]; then
        echo "CLEANUP: Skipping Docker cleanup because Docker not installed"
        return 0
    fi

    echo "CLEANUP: Stop all running containers and remove unwanted images"
    sudo docker ps -q -a | xargs -r sudo docker rm -f
    [[ $? -ne 0 ]] && fail=true
    sudo docker images --format "{{.Repository}}:{{.Tag}}" | \
        grep -Ev "^docker\.io/(${DOCKER_REPOS_WHITELIST})[:/].*" | \
        xargs -r sudo docker rmi -f
    [[ $? -ne 0 ]] && fail=true

    if ! $fail; then
        return 0
    fi
    # if we've got here, something went wrong
    echo "ERROR: Failed to clean docker images"
    return 1
}

main() {
    local workspace="${1?}"
    local failed=false

    echo "###############################################################"
    echo "#    Cleaning up slave                                        #"
    echo "###############################################################"
    sudo df -h || :
    echo "---------------------------------------------------------------"
    cleanup_postgres || failed=true
    cleanup_journal || failed=true
    cleanup_var || failed=true
    cleanup_logs || failed=true
    cleanup_workspaces "$workspace" || failed=true
    cleanup_home || failed=true
    cleanup_loop_devices || failed=true
    cleanup_lago || failed=true
    cleanup_libvirt || failed=true
    cleanup_docker || failed=true
    echo "---------------------------------------------------------------"
    sudo df -h || :
    if $failed; then
        echo "###############################################################"
        echo "#    Slave cleanup done: Some steps FAILED!                   #"
        echo "###############################################################"
        return 1
    else
        echo "###############################################################"
        echo "#    Slave cleanup done: SUCCESS                              #"
        echo "###############################################################"
        return 0
    fi
}


main "$WORKSPACE"
