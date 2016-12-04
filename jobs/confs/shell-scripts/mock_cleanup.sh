#!/bin/bash -xe
echo "shell-scripts/mock_cleanup.sh"

shopt -s nullglob


WORKSPACE="$PWD"

# Make clear this is the cleanup, helps reading the jenkins logs
cat <<EOC
_______________________________________________________________________
#######################################################################
#                                                                     #
#                               CLEANUP                               #
#                                                                     #
#######################################################################
EOC


# Archive the logs, we want them anyway
logs=(
    ./*log
    ./*/logs
)

if [[ "$logs" ]]; then
    for log in "${logs[@]}"
    do
        echo "Copying ${log} to exported-artifacts"
        mv $log exported-artifacts/
    done
fi

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
        sudo umount --lazy "$mount" \
        || {
            echo "ERROR:  Failed to umount $mount."
            failed=true
        }
    done
done

# Clean any leftover chroot from other jobs
for mock_root in /var/lib/mock/*; do
    this_chroot_failed=false
    mounts=($(mount | awk '{print $3}' | grep "$mock_root")) || :
    if [[ "$mounts" ]]; then
        echo "Found mounted dirs inside the chroot $mock_root." \
             "Trying to umount."
    fi
    for mount in "${mounts[@]}"; do
        sudo umount --lazy "$mount" \
        || {
            echo "ERROR:  Failed to umount $mount."
            failed=true
            this_chroot_failed=true
        }
    done
    if ! $this_chroot_failed; then
        sudo rm -rf "$mock_root"
    fi
done

if $failed; then
    echo "Aborting."
    exit 1
fi

# remove mock caches that are older then 2 days:
find /var/cache/mock/ -mindepth 1 -maxdepth 1 -type d -mtime +2 -print0 | \
    xargs -0 -tr sudo rm -rf
# We make no effort to leave around caches that may still be in use because
# packages installed in them may go out of date, so may as well recreate them

# restore the permissions in the working dir, as sometimes it leaves files
# owned by root and then the 'cleanup workspace' from jenkins job fails to
# clean and breaks the jobs
sudo chown -R "$USER" "$WORKSPACE"

# Drop all left over libvirt domains
for UUID in $(virsh list --all --uuid); do
  virsh destroy $UUID || :
  sleep 2
  virsh undefine --remove-all-storage --storage vda --snapshots-metadata $UUID || :
done
