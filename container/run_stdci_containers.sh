#!/bin/bash -xe
# run_stdci_containers.sh - Script to deploy multiple stdci containers in the
#                           host. The script receives a jenkins url as the
#                           first param and a space separated JNLP secrets.
#                           It then creates slots for every container-slave
#                           under $STDCI_DATA_DIR and mounts it in the
#                           container.

STDCI_DATA_DIR="/var/lib/stdci"
STDCI_IMAGE_NAME="stdci:current-slave-image"
RUNTIME_USERNAME=jenkins

main() {
    local jenkins_server="${1:?ERROR: You have to specify jenkins server url}"
    shift
    local secrets=("${@}");
    local arg_count=${#@}
    mkdir -p "$STDCI_DATA_DIR"

    local hostname; hostname="$(hostname)"
    local base_cmd container_name extras
    for secret in "${secrets[@]}"; do

        container_name="$hostname-container-${arg_count}"
        local extras; IFS=" " read -r -a extras <<< \
            "$(prep_slave_slot "$arg_count" "$secret")"

        base_cmd=(
            --privileged "--name=$container_name" -d
            -e "STDCI_SLAVE_CONTAINER_NAME=$container_name"
            -e "JENKINS_URL=$jenkins_server"
            -e "JENKINS_AGENT_NAME=$container_name"
            -e "JENKINS_SECRET=$secret"
            -e "CI_RUNTIME_UNAME=$RUNTIME_USERNAME"
            -v '/var/run/docker.sock:/root/docker.sock'
        )

        docker run "${base_cmd[@]}" "${extras[@]}" "$STDCI_IMAGE_NAME"

        (( --arg_count ))
    done
}

prep_slave_slot() {
    local slave_count="${1:?}"
    local slave_home="${STDCI_DATA_DIR}/container-slaves/${slave_count}"

    mkdir -p "$slave_home"

    local cmd
    cmd+=( "$(prep_runtime_user_home "$slave_home")" )
    cmd+=( "$(prep_lago_dirs "$slave_home")" )
    cmd+=( "$(prep_mock_dirs "$slave_home")" )

    printf "%s " "${cmd[@]}"
}

prep_lago_dirs() {
    local slave_home="${1:?}"
    local lago_home="${slave_home}/var/lib/lago"
    local lago_subnets_dir="${lago_home}/subnets"

    mkdir -p "$lago_subnets_dir"
    local real_lago_home; real_lago_home="$(realpath "$lago_home")"

    local -a cmd; cmd=(
        -v "$real_lago_home:/var/lib/lago"
    )
    printf "%s " "${cmd[@]}"
}

prep_mock_dirs() {
    local slave_home="${1:?}"
    local mock_dir="${slave_home}/mock"
    local mock_cache="${mock_dir}/cache"
    local mock_lib="${mock_dir}/lib"

    mkdir -p "$mock_lib" "$mock_cache"
    local real_mock_lib; real_mock_lib="$(realpath "$mock_lib")"
    local real_mock_cache; real_mock_cache="$(realpath "$mock_cache")"

    local -a cmd; cmd=(
        -v "$real_mock_lib:/var/lib/mock"
        -v "$real_mock_cache:/var/cache/mock"
    )
    printf "%s " "${cmd[@]}"
}

prep_runtime_user_home() {
    local slave_home="${1:?}"
    local runtime_user_home="${slave_home}/home/jenkins"
    local runtime_uid; runtime_uid="$(id -u "$RUNTIME_USERNAME")"
    local runtime_gid; runtime_gid="$(id -g "$RUNTIME_USERNAME")"

    mkdir -p "$runtime_user_home"
    chown -R "$runtime_uid":"$runtime_gid" "$runtime_user_home"
    local real_runtime_user_home
    real_runtime_user_home="$(realpath "$runtime_user_home")"

    local cmd; cmd=(
        -v "$real_runtime_user_home":"$real_runtime_user_home"
        -e "JENKINS_AGENT_WORKDIR=$real_runtime_user_home"
        -e "CI_RUNTIME_UID=$runtime_uid"
    )
    printf "%s " "${cmd[@]}"
}

main "$@"
