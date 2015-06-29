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
            -Po "(?=<config_opts\['root'\] = ')[^']*" \
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

if $failed; then
    echo "Aborting."
    exit 1
fi

# remove mock system cache, we will setup proxies to do the caching and this
# takes lots of space between runs
sudo rm -Rf /var/cache/mock/*
