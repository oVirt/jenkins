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


# builds the iso
#parameters
#      1 : parameter to indicate the extra ks file to run
function build_iso {{
    pushd .
    cd "$OVIRT_NODE_BASE"
    cat > extra-recipe.ks <<EOF_ks
%packages --excludedocs --nobase
ovirt-node-plugin-vdsm
ovirt-node-plugin-hosted-engine
%end
EOF_ks
    cd "$OVIRT_NODE_BASE"/ovirt-node-iso
    ./autogen.sh \
        --with-recipe=../ovirt-node/recipe \
        --with-extra-recipe=../extra-recipe.ks
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
    if [[ ! -d $OVIRT_NODE_BASE/ovirt-node ]] ; then
        die "No node base found"
    fi
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
    make clean \
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
    clean_iso
fi

if $do_build; then
    build_iso
fi

if $do_publish_rpms; then
    cp "$OVIRT_CACHE_DIR"/ovirt/binary/*.iso exported-artifacts/
fi
