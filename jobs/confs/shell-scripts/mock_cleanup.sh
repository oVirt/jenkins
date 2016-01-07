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
    tar cvzf exported-artifacts/logs.tgz "${logs[@]}"
    rm -rf "${logs[@]}"
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
        sudo umount "$mount" \
        || {
            echo "ERROR:  Failed to umount $mount."
            failed=true
        }
    done
done

# Try to cleanup leftover loopback devices in this workspace (or a mock root
# from this workspace). /build/diskFOOBAR.img are orphaned from
# livemedia-creator. Grab those also
loops=($(losetup -a \
    | grep -E "$WORKSPACE|\(build/disk" \
    | awk '{print $1}' \
    | sed -e 's/://'\
)) || :
if [[ "$loops" ]]; then
    echo "Found orphaned or left over loopback devices. Removing them"
fi
for loop in "${loops[@]}"; do
    # Check devmapper, since it can't be removed from losetup if dm holds it
    dm_device=$(dmsetup info | grep $loop | awk '{print $2}') || :
    [[ "$dm_device" ]] \ && dmsetup remove $dm_device \
        || {
            echo "ERROR:  Failed to dmsetup remove $dm_device."
            failed=true
        }
    losetup -d /dev/$loop \
    || {
        echo "ERROR:  Failed to losetup -d /dev/$loop."
        failed=true
    }
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
        sudo umount "$mount" \
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

# remove mock system cache, we will setup proxies to do the caching and this
# takes lots of space between runs
shopt -u nullglob
sudo rm -Rf /var/cache/mock/*

# restore the permissions in the working dir, as sometimes it leaves files
# owned by root and then the 'cleanup workspace' from jenkins job fails to
# clean and breaks the jobs
sudo chown -R "$USER" "$WORKSPACE"
