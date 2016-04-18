#!/bin/bash -xe
echo "shell-scripts/build-local-ovirt-node-iso.sh"
#this scripts build ovirt-node and ovirt-node-is projects

DISTRO="{distro}"

# the die on error function
function die {{
    echo "$1"
    exit 1
}}


#sets the env variables required for the rest
function set_env {{
    export CACHE="$PWD"/build
    export OVIRT_NODE_BASE="$PWD"
    export OVIRT_CACHE_DIR="$CACHE/$DISTRO"
    export PATH=$PATH:/usr/sbin
}}


# builds the iso
#parameters
#      1 : parameter to indicate the extra ks file to run
function build_iso {{
    pushd .
    cd "$OVIRT_NODE_BASE"
    cd "$OVIRT_NODE_BASE"/ovirt-node-iso
    ./autogen.sh
    chmod +x recepie-downloader.sh
    ./recepie-downloader.sh install
    if  ! make iso publish ; then
        die "ISO build failed"
    fi
    if ! cp ovirt-node-image.ks "$OVIRT_CACHE_DIR"/ ; then
        die "can't find source kick start , you should never reach here"
    fi
    popd
}}

#the prereqs
function check_pre {{
    if [[ ! -d $OVIRT_NODE_BASE/ovirt-node-iso ]] ; then
        die "No node-ISO base found"
    fi
}}

function clean_iso {{
    pushd .
    local clean_failed=false
    sudo rm -rf "$CACHE"
    cd "$OVIRT_NODE_BASE"/ovirt-node-iso
    # get rid of old makefiles
    git clean -dfx
    # generate new makefiles
    ./autogen.sh
    chmod +x recepie-downloader.sh
    ./recepie-downloader.sh remove
    ./recepie-downloader.sh remove-repo
    make clean \
        || clean_failed=true
    popd
    if $clean_failed; then
        return 1
    else
        return 0
    fi
}}

#patch jenkins packages
sudo yum install sssd-client -y || true

set_env
check_pre

for dir in exported-artifacts; do
    rm -Rf "$dir"
    mkdir -p "$dir"
done

clean_iso
build_iso

cp "$OVIRT_CACHE_DIR"/ovirt/binary/*.iso exported-artifacts/
cp "$OVIRT_CACHE_DIR"/ovirt/noarch/*.rpm exported-artifacts/


#lets extract staff
iso=$(find "$OVIRT_CACHE_DIR/ovirt/binary" -mindepth 1 -maxdepth 1 -type f -name '*.iso' -print -quit)
rm -rf "./tmp*"
mount_dir=$(mktemp -d -p "$WORKSPACE")
sudo mount -t iso9660 -o loop "$iso" "$mount_dir"
cp $mount_dir/isolinux/manifest-srpm.txt exported-artifacts/
cp $mount_dir/isolinux/manifest-rpm.txt exported-artifacts/
sudo umount "$mount_dir"
rm -rf "$WORKSPACE/$mount_dir"