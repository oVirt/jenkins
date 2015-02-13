#!/bin/bash -xe
echo "shell-scripts/mock_cleanup.sh"

shopt -s nullglob


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
pushd "$WORKSPACE"/exported-artifacts
logs=(*log *_pkgs "$WORKSPACE"/*log)
if [[ "$logs" ]]; then
    tar cvzf logs.tgz "${logs[@]}"
    rm -f *log *_pkgs
fi
popd

failed=false

mock_dir="$WORKSPACE/mock"
# stop any processes running inside the chroot
chroots=("$WORKSPACE"/mock/*)
for chroot in "${chroots[@]}"; do
    echo "Cleaning up chroot $chroot"
    ### Generate the mock configuration
    pushd "$WORKSPACE"/jenkins/mock_configs
    mock_conf="${chroot##*/}"
    base_conf="${mock_conf%%x86_64*}x86_64"
    echo "#### Generating mock configuration"
    ./mock_genconfig \
        --name="$mock_conf" \
        --base="$base_conf.cfg" \
        --option="basedir=$WORKSPACE/mock/" \
    > "$mock_conf.cfg"
    cat "$mock_conf.cfg"
    popd

    my_mock="/usr/bin/mock"
    my_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
    my_mock+=" --root=$mock_conf"
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

    mounts=($(mount | awk '{print $3}' | grep "$chroot")) || :
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
sudo rm -Rf mock mock-cache

# remove mock system cache, we will setup proxies to do the caching and this
# takes lots of space between runs
sudo rm -Rf /var/cache/mock/*
