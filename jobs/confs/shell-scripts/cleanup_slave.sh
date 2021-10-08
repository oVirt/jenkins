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
    if ! can_sudo umount; then
        echo "Skipping umount - no sudo permissions"
        return
    fi
    for inner_dir in "${inner_dirs[@]}"; do
        sudo -n umount --lazy "$inner_dir" \
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
        rm -Rf "$dir" || {
            [[ -d "$dir" ]] && sudo -n rm -Rf "$dir" || echo "Can't sudo rm $dir"
        }
    else
        rm -f "$dir" || {
            [[ -e "$dir" ]] && sudo -n rm -f "$dir" || echo "Can't sudo rm $dir"
        }
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
    if ! can_sudo rm; then
        log WARN "Skipping /var cleanup - not enough sudo permissions"
        return 0
    fi
    local res=0
    local dir
    echo "Cleaning up /var/tmp"
    for dir in /var/tmp/* /var/lib/ovirt-*; do
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
    if ! can_sudo rm psql; then
        log WARN "Skipping postgres cleanup - not enough sudo permissions"
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
    if ! can_sudo rm bash dmesg; then
        log WARN: "Skipping system log cleanup - not enough sudo permissions"
        return 0
    fi
    echo "Emptying some common logs"
    local log empty_logfiles remove_logfiles
    empty_logfiles=(
        /var/log/wtmp
    )
    remove_logfiles=(
        /var/log/messages-*
        /var/log/secure-*
    )
    for logf in "${empty_logfiles[@]}"; do
        [[ -f "$log" ]] \
            && sudo -n bash -c "> $logf" \
            && echo "    $log"
    done
    for logf in "${remove_logfiles[@]}"; do
        [[ -f "$logf" ]] \
            && safe_remove "$logf" \
            && echo "    $logf"
    done
    sudo -n dmesg -c >/dev/null
    echo "Done"
    return 0
}

cleanup_journal() {
    if ! can_sudo systemctl journalctl; then
        log WARN "Skipping journal cleanup - no sudo permissions"
        return 0
    fi
    echo "Cleaning up journal logs (if any)"
    if ! sudo -n systemctl status systemd-journald &>/dev/null; then
        echo "  journald not running, skipping"
        return 0
    fi
    # Vacuum journal
    sudo -n journalctl --vacuum-time=14d --vacuum-size=512M
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
    if ! can_sudo ip; then
        log WARN "Skipping Lago network cleanup - no sudo permissions for 'ip'"
        return 0
    fi
    local links link
    local failed=false
    # remove lago-type interfaces, that is, 8chars of hash + '-some_tag'
    # or 4 chars of hash + 6 chars of hash
    links=(
        $( \
            sudo -n ip link show \
            | grep -Po '^[[:alnum:]]*: [[:alnum:]]{8}-[^:]*' \
            | awk '{print $2}' \
        )
        $( \
            sudo -n ip link show \
            | grep -Po '^[[:alnum:]]*: [[:alnum:]]{4}-[[:alnum:]]{6}[^:]*' \
            | awk '{print $2}' \
        )
    )
    for link in "${links[@]}"; do
        #If the interface has an '@' the name is before it
        link="${link%%@*}"
        echo "Removing interface $link"
        sudo -n ip link delete "$link" \
        || {
            failed=true
            log ERROR "Failed to cleanup interface $link"
        }
    done
    if $failed; then
        return 1
    fi
    return 0
}

is_docker_using_devicemapper() {
    # Check if docker is using devicemapper as it's storage driver
    if grep -q "devicemapper" <<< $(sudo docker info 2>/dev/null); then
        return 0
    fi
    return 1
}

cleanup_loop_devices() {
    # Too risky to run it from a container... untill we have a proper solution
    # for containers, don't run it if we're in a container slave.
    [[ -n "$STDCI_SLAVE_CONTAINER_NAME" ]] && return 0
    if ! can_sudo dmsetup || ! can_sudo losetup; then
        log WARN "Skipping loop device cleanup - no sudo for dmsetup/losetup"
        return 0
    fi
    # If docker is using devicemapper then we remove all dm pools
    # except for the pool(s) used by docker
    local failed=false

    echo "Making sure there are no device mappings..."
    if test_and_start_docker && is_docker_using_devicemapper; then
        clean_device_mappings_except_docker
    else
        echo "Removing all mappings..."
        sudo -n dmsetup remove_all || :
    fi
    echo "Removing the used loop devices..."
    sudo -n losetup -D || :
    if [[ "$failed" == "true" ]]; then
        echo "Failed to free some loop devices:"
        sudo -n losetup
        echo "--- device mappings"
        sudo -n dmsetup info
        return 1
    fi
    return 0
}

test_and_start_docker() {
    # Check if docker binary exists on the host and make sure it runs
    if [[ -x "/bin/docker" ]]; then
        sudo systemctl start docker && return 0
    fi
    return 1
}

get_docker_dm_storage_pool() {
    # Get the devicemapper pool docker 'thinks' it was assigned with
    grep -oE "docker-.+-pool" <<< $(sudo docker info 2>/dev/null)
}

clean_device_mappings_except_docker() {
    local all_dm_pools_no_docker

    if ! grep -q "$(get_docker_dm_storage_pool)" <<< $(sudo dmsetup ls); then
        # Docker thinks it's been assigned with a different device
        # than what devicemapper actually did
        echo "Found error in Docker storage configuration. Restarting Docker"
        sudo -n systemctl stop docker
        sudo -n rm -rf /var/lib/docker/
        sudo -n systemctl start docker
    fi
    all_dm_pools_no_docker=(
        $(sudo -n dmsetup ls | \
          grep -v "$(get_docker_dm_storage_pool)" | \
          cut -d$'\t' -f1)
    )
    [[ ${#all_dm_pools_no_docker[@]} -ne 0 ]] && \
        sudo -n dmsetup remove "${all_dm_pools_no_docker[@]}" || :
    return 0
}

cleanup_lago() {
    cleanup_lago_network_interfaces || :
}

kill_lago_processes() {
    if ! can_sudo "pkill -f lago"; then
        log WARN "Skipping kill lago processes - not enough sudo permissions"
        return 0
    fi
    sudo -n pkill -f lago || :
}

cleanup_libvirt_vms() {
    # Drop all left over libvirt domains
    for UUID in $(sudo virsh list --all --uuid); do
        echo "Removing domain with UUID: $UUID"
        sudo -nE virsh destroy $UUID || :
        sleep 2
        sudo -nE virsh undefine --remove-all-storage --snapshots-metadata $UUID || :
    done
}

cleanup_libvirt_networks() {
    local links \
        link
    local failed=false
    # remove lago-type interfaces, that is, 8chars of hash + '-some_tag'
    links=($( sudo -n virsh net-list --name | grep -vF default ))
    for link in "${links[@]}"; do
        echo "Removing virtual network: $link"
        sudo -n virsh net-destroy "$link" \
        || {
            failed=true
            log ERROR "Failed to cleanup virtual network: $link"
        }
    done
    if $failed; then
        return 1
    fi
    return 0
}

cleanup_libvirt() {
    if ! can_sudo virsh; then
        log WARN "Skipping libvirt cleanup - no sudo permissions for virsh"
        return 0
    fi
    cleanup_libvirt_vms || :
    cleanup_libvirt_networks || :
    sudo -n service libvirtd restart || :
}

rollback_os_repos() {
    local failed=false
    local yum_conf

    if ! can_sudo mv; then
        log WARN "Skipping Rolling back uncommitted OS repo update ; no sudo permissions for mv"
        return 0
    fi

    for yum_conf in /etc{{/yum,}/yum.conf,/dnf/dnf.conf}; do
        [[ -f "$yum_conf" ]] || continue
        [[ -f "${yum_conf}.rbk" ]] || continue
        echo "Rolling back uncommitted OS repo update: $yum_conf"
        sudo -n mv --force "${yum_conf}.rbk" "$yum_conf" || failed=true
    done
    if $failed; then
        return 1
    else
        return 0
    fi
}

rollback_known_hosts() {
    local known_hosts="$HOME/.ssh/known_hosts"
    rollback_file "$known_hosts"
}

rollback_file() {
    local file="${1:?}"
    local file_rbk="${file}.rbk"

    [[ -f "$file" ]] && [[ -f "$file_rbk" ]] || return 0

    if ! can_sudo mv; then
        log WARN "Skipping Rolling back uncommited file: $file ; no sudo permissions for mv"
        return 0
    fi

    echo "Rolling back uncommited file: $file"
    sudo -n mv --force "$file_rbk" "$file" || return $?

    return 0
}

cleanup_old_artifacts() {
    safe_remove "$WORKSPACE/exported-artifacts" &&
        mkdir "$WORKSPACE/exported-artifacts"
}

cleanup_dev_shm() {
    for f in /dev/shm/ost /dev/shm/yum* /dev/shm/*.rpm; do
        echo cleanup_dev_shm: Removing "${f}"
        safe_remove "${f}"
    done
}

UMOUNT_RETRIES="${UMOUNT_RETRIES:-3}"
UMOUNT_RETRY_DELAY="${UMOUNT_RETRY_DELAY:-1s}"

safe_umount() {
    local mount="${1:?}"
    local attempt
    for ((attempt=0 ; attempt < $UMOUNT_RETRIES ; attempt++)); do
        # If this is not the 1st time through the loop, Sleep a while to let
        # the problem "solve itself"
        [[ attempt > 0 ]] && sleep "$UMOUNT_RETRY_DELAY"
        # Try to umount
        sudo -n umount --lazy "$mount" && return 0
        # See if the mount is already not there despite failing
        findmnt --kernel --first-only "$mount" > /dev/null || return 0
    done
    echo "ERROR:  Failed to umount $mount."
    return 1
}

wipe_other_chroots() {
    # Clean any leftover chroot from other jobs
    if ! can_sudo rm; then
        echo "Skipping cleanup of mock chroots - no sudo permissions"
        return
    fi
    local mock_root this_chroot_failed mount mounts
    local failed=false

    for mock_root in /var/lib/mock/*; do
        this_chroot_failed=false
        mounts=($(cut -d\  -f2 /proc/mounts | grep "$mock_root" | sort -r)) || :
        if [[ "$mounts" ]]; then
            echo "Found mounted dirs inside the chroot $mock_root." \
                 "Trying to umount."
        fi
        for mount in "${mounts[@]}"; do
            safe_umount "$mount" && continue
            # If we got here, we failed $UMOUNT_RETRIES attempts so we should make
            # noise
            failed=true
            this_chroot_failed=true
        done
        if ! $this_chroot_failed; then
            sudo -n rm -rf "$mock_root"
        fi
    done
    # Return $failed from this function
    ! $failed
}

wipe_old_caches() {
    # remove mock caches that are older then 2 days:
    if ! can_sudo rm; then
        echo "Skipping cleanup of mock caches - no sudo permissions"
        return
    fi
    find /var/cache/mock/ -mindepth 1 -maxdepth 1 -type d -mtime +2 -print0 | \
        xargs -0 -tr sudo -n rm -rf
    # We make no effort to leave around caches that may still be in use because
    # packages installed in them may go out of date, so may as well recreate them
}

cleanup_mock() {
    local failed=false

    wipe_other_chroots || failed=true
    wipe_old_caches || failed=true

    # Return $failed from this function
    ! $failed
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

main() {
    local workspace="${1?}"
    local failed=false

    echo "###############################################################"
    echo "#    Cleaning up slave                                        #"
    echo "###############################################################"
    if ! can_sudo df; then
        echo "Skipping df - no sudo permissions"
    else
        sudo -n df -h || df -h || :
    fi
    echo "---------------------------------------------------------------"
    rollback_os_repos || failed=true
    rollback_known_hosts || failed=true
    cleanup_postgres || failed=true
    cleanup_journal || failed=true
    cleanup_var || failed=true
    cleanup_logs || failed=true
    cleanup_workspaces "$workspace" || failed=true
    cleanup_home || failed=true
    cleanup_loop_devices || failed=true
    cleanup_lago || failed=true
    cleanup_libvirt || failed=true
    kill_lago_processes || failed=true
    cleanup_old_artifacts || failed=true
    cleanup_dev_shm || failed=true
    cleanup_mock || failed=true
    echo "---------------------------------------------------------------"
    if ! can_sudo df; then
        echo "Skipping df - no sudo permissions"
    else
        sudo -n df -h || df -h || :
    fi
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
