#!/bin/bash -xe
echo "shell-scripts/build-local-ovirt-node.sh"
#this scripts build ovirt-node and ovirt-node-is projects

DISTRO="{distro}"

do_build=true
do_clean={clean_pre}

do_publish_rpms={publish_rpms}

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


#builds the node
function build_node {{
    pushd .
    cd "$OVIRT_NODE_BASE"/ovirt-node
    ./autogen.sh --with-image-minimizer
    if ! make publish ; then
        die "Node building failed"
    fi
    popd
}}


#the prereqs
function check_pre {{
    if [[ ! -d $OVIRT_NODE_BASE/ovirt-node ]] ; then
        die "No node base found"
    fi
}}


function clean_node {{
    pushd .
    local clean_failed=false
    sudo rm -rf "$CACHE"
    cd "$OVIRT_NODE_BASE"/ovirt-node
    # get rid of old makefiles
    git clean -dfx
    # generate new makefiles
    ./autogen.sh
    make distclean \
        || clean_failed=true
    popd
    if $clean_failed; then
        return 1
    else
        return 0
    fi
}}


set_env
check_pre

for dir in exported-artifacts; do
    rm -Rf "$dir"
    mkdir -p "$dir"
done

if $do_clean; then
    clean_node
fi

if $do_build; then
    build_node
fi

if $do_publish_rpms; then
    rm -rf "$OVIRT_CACHE_DIR"/ovirt/RPMS/noarch/ovirt-node-plugin-rhn*.rpm
    cp "$OVIRT_CACHE_DIR"/ovirt/RPMS/noarch/ovirt-node*.rpm exported-artifacts/
fi

