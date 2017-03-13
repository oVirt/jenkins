#!/bin/bash -x
echo "shell-scripts/mock_cleanup.sh"
# Make clear this is the cleanup, helps reading the jenkins logs
cat <<EOC
_______________________________________________________________________
#######################################################################
#                                                                     #
#                               CLEANUP                               #
#                                                                     #
#######################################################################
EOC

shopt -s nullglob

WORKSPACE="${WORKSPACE:-$PWD}"
UMOUNT_RETRIES="${UMOUNT_RETRIES:-3}"
UMOUNT_RETRY_DELAY="${UMOUNT_RETRY_DELAY:-1s}"


docker_cleanup () {
    # for now, we want to keep only centos and fedora official images
    local -r DOCKER_REPOS_WHITELIST="centos|fedora|"
    local fail=false

    echo "CLEANUP: Stop all running containers and remove unwanted images"
    sudo docker ps -q -a | xargs -r sudo docker rm -f
    [[ $? -ne 0 ]] && fail=true
    sudo docker images --format "{{.Repository}},{{.ID}}" | \
        sed -nr \
            -e "/^docker.io\/($DOCKER_REPOS_WHITELIST)(\/?[^\/]+)?,/d" \
            -e "s/^.*,(.*)/\1/p" | \
        xargs -r sudo docker rmi -f
    [[ $? -ne 0 ]] && fail=true

    sudo systemctl restart docker
    [[ $? -ne 0 ]] && fail=true

    if ! $fail; then
        return 0
    fi
    # if we've got here, something went wrong
    echo "ERROR: Failed to clean docker images"
    return 1
}


safe_umount() {
    local mount="${1:?}"
    local attempt
    for ((attempt=0 ; attempt < $UMOUNT_RETRIES ; attempt++)); do
        # If this is not the 1st time through the loop, Sleep a while to let
        # the problem "solve itself"
        [[ attempt > 0 ]] && sleep "$UMOUNT_RETRY_DELAY"
        # Try to umount
        sudo umount --lazy "$mount" && return 0
        # See if the mount is already not there despite failing
        findmnt --kernel --first "$mount" > /dev/null && return 0
    done
    echo "ERROR:  Failed to umount $mount."
    return 1
}

# restore the permissions in the working dir, as sometimes it leaves files
# owned by root and then the 'cleanup workspace' from jenkins job fails to
# clean and breaks the jobs
sudo chown -R "$USER" "$WORKSPACE"
sudo chmod -R u+w "$WORKSPACE"

# stop any processes running inside the chroot
failed=false
mock_confs=("$WORKSPACE"/*/mocker*)
# Clean current jobs mockroot if any
for mock_conf_file in "${mock_confs[@]}"; do
    [[ "$mock_conf_file" ]] || continue
    echo "Cleaning up mock $mock_conf"
    mock_root="${mock_conf_file##*/}"
    mock_root="${mock_root%.*}"
    my_mock="/usr/bin/mock"
    my_mock+=" --configdir=${mock_conf_file%/*}"
    my_mock+=" --root=${mock_root}"
    my_mock+=" --resultdir=$WORKSPACE"

    #TODO: investigate why mock --clean fails to umount certain dirs sometimes,
    #so we can use it instead of manually doing all this.
    echo "Killing all mock orphan processes, if any."
    $my_mock \
        --orphanskill \
    || {
        echo "ERROR:  Failed to kill orphans on $chroot."
        failed=true
    }

    mock_root="$(\
        grep \
            -Po "(?<=config_opts\['root'\] = ')[^']*" \
            "$mock_conf_file" \
    )" || :
    [[ "$mock_root" ]] || continue
    mounts=($(mount | awk '{print $3}' | grep "$mock_root")) || :
    if [[ "$mounts" ]]; then
        echo "Found mounted dirs inside the chroot $chroot. Trying to umount."
    fi
    for mount in "${mounts[@]}"; do
        safe_umount "$mount" || failed=true
    done
done

# Clean any leftover chroot from other jobs
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
        sudo rm -rf "$mock_root"
    fi
done

# remove mock caches that are older then 2 days:
find /var/cache/mock/ -mindepth 1 -maxdepth 1 -type d -mtime +2 -print0 | \
    xargs -0 -tr sudo rm -rf
# We make no effort to leave around caches that may still be in use because
# packages installed in them may go out of date, so may as well recreate them

# Drop all left over libvirt domains
for UUID in $(virsh list --all --uuid); do
  virsh destroy $UUID || :
  sleep 2
  virsh undefine --remove-all-storage --storage vda --snapshots-metadata $UUID || :
done

if [[ -x /bin/docker ]]; then
    #Cleanup docker leftovers.
    docker_cleanup || failed=true
fi

if $failed; then
    echo "Cleanup script failed, propegating failure to job"
    exit 1
fi
