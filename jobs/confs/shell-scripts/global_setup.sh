#!/bin/bash -xe
echo "shell-scripts/global_setup.sh"
#
# Executes all the commands that must be run on any job
#
shopt -s nullglob

main() {
    local failed=false

    mk_wokspace_tmp
    extra_packages || failed=true
    docker_setup || failed=true

    # If we failed in any step, abort to avoid breaking the host
    if $failed; then
        echo "Aborting."
        return 1
    fi
    return 0
}

mk_wokspace_tmp() {
    rm -rf "$WORKSPACE/tmp"
    mkdir -p "$WORKSPACE/tmp"
}

extra_packages() {
    # Add extra packages we need for mock_runner.sh
    if [[ -e '/usr/bin/dnf' ]]; then
        sudo dnf -y install python3-PyYAML PyYAML
    else
        sudo yum -y install python34-PyYAML PyYAML
    fi
}

docker_setup () {
    #Install docker engine and start the service
    sudo yum -y install docker
    if ! sudo systemctl start docker; then
        echo "[DOCKER SETUP] Failed to start docker.service"
        return 1
    fi
    echo "[DOCKER SETUP] Docker service started"
    return 0
}

main "@$"
