#!/bin/bash -xe
echo "shell-scripts/build-local-ovirt-node.sh"
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
    export OVIRT_LOCAL_REPO=file://"$OVIRT_CACHE_DIR"/ovirt
}}


# builds the iso
#parameters
#      1 : parameter to indicate the extra ks file to run
function build_iso {{
    cd "$OVIRT_NODE_BASE"/ovirt-node-iso
    ./autogen.sh \
        --with-recipe=../ovirt-node/recipe \
        "$EXTRA_RECIPE"
    if  ! make iso publish ; then
        die "ISO build failed"
    fi
    if ! cp ovirt-node-image.ks "$OVIRT_CACHE_DIR"/ ; then
        die "can't find source kick start , you should never reach here"
    fi
    cd "$OVIRT_NODE_BASE"
}}


#builds the node
function build_node {{
    cd "$OVIRT_NODE_BASE"/ovirt-node
    ./autogen.sh --with-image-minimizer
    if ! make publish ; then
        die "Node building failed"
    fi
    cd "$OVIRT_NODE_BASE"
}}


#the prereqs
function check_pre {{
    if [[ ! -d $OVIRT_NODE_BASE/ovirt-node ]] ; then
        die "No node base found"
    fi
    if [[ ! -d $OVIRT_NODE_BASE/ovirt-node-iso ]] ; then
        die "No node-ISO base found"
    fi
}}


function clean {{
    local clean_failed=false
    sudo rm -rf "$CACHE"
    cd "$OVIRT_NODE_BASE"/ovirt-node
    # get rid of old makefiles
    git clean -dfx
    # generate new makefiles
    ./autogen.sh
    make distclean \
        || clean_failed=true
    cd ..
    cd "$OVIRT_NODE_BASE"/ovirt-node-iso
    # get rid of old makefiles
    git clean -dfx
    # generate new makefiles
    ./autogen.sh
    make clean \
        || clean_failed=true
    cd ..
    if $clean_failed; then
        return 1
    else
        return 0
    fi
}}


do_build_iso=true
do_build_node=true
do_clean=true
set_env
check_pre

for dir in exported-artifacts; do
    rm -Rf "$dir"
    mkdir -p "$dir"
done

if $do_clean; then
    clean
fi

if $do_build_node; then
    build_node
fi

if $do_build_iso; then
    build_iso
fi

mv "$OVIRT_CACHE_DIR"/ovirt/binary/*.iso exported-artifacts/
