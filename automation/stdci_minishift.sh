#!/bin/bash -ex
# stdci_minishift.sh - Shell functions for handling minishift for STDCI scripts.
#                      This file should generally be sourced by other scripts.
#
source scripts/safe_download.sh

minishift::setup() {
    minishift::verify_dir
    minishift::verify_bin
    minishift::install_driver
}

minishift::verify_dir() {
    [[ -e ~/.minishift ]] && return
    if [[ $UID -eq 0 ]] && [[ -d /var/host_cache ]]; then
        export MINISHIFT_HOME=/var/cache/stdci_minishift
        mkdir -p /var/host_cache/stdci_minishift
        ln -s /var/host_cache/stdci_minishift "$MINISHIFT_HOME"
    else
        export MINISHIFT_HOME=~/.minishift
        mkdir -p "$MINISHIFT_HOME"
    fi
}

minishift::verify_bin() {
    local dl_site=https://github.com/minishift/minishift/releases/download/
    export MINISHIFT_BIN_DIR="$MINISHIFT_HOME/bin"

    mkdir -p $MINISHIFT_HOME/package
    safe_download -d sha256 \
        -a minishift::extract_bin \
        $MINISHIFT_HOME/package.lock \
        "$dl_site/v1.28.0/minishift-1.28.0-linux-amd64.tgz" \
        $MINISHIFT_HOME/package.tgz
    if [[ -x "$MINISHIFT_BIN_DIR/minishift" ]]; then
        [[ "$PATH" == "$MINISHIFT_BIN_DIR" ]] ||
            [[ "$PATH" == "$MINISHIFT_BIN_DIR":* ]] ||
            [[ "$PATH" == *:"$MINISHIFT_BIN_DIR" ]] ||
            [[ "$PATH" == *:"$MINISHIFT_BIN_DIR":* ]] ||
            PATH="$MINISHIFT_BIN_DIR:$PATH"
    else
        return 1
    fi
}

minishift::extract_bin() {
    echo "extracting minishift"
    local package="${1:?}"
    mkdir -p "$MINISHIFT_BIN_DIR"
    tar -xOzf "$package" '*/minishift' > "$MINISHIFT_BIN_DIR/minishift"
    chmod +x "$MINISHIFT_BIN_DIR/minishift"
}

minishift::install_driver() {
    local dl_site
    dl_site=https://github.com/dhiltgen/docker-machine-kvm/releases/download

    mkdir -p "$MINISHIFT_BIN_DIR"
    safe_download -d md5 \
        -s fb2ded7b5b20400ef66f0adbc384364e \
        "$MINISHIFT_BIN_DIR/docker-machine-driver-kvm.lock" \
        "$dl_site/v0.10.0/docker-machine-driver-kvm-centos7" \
        "$MINISHIFT_BIN_DIR/docker-machine-driver-kvm"
    chmod +x "$MINISHIFT_BIN_DIR/docker-machine-driver-kvm"
}
