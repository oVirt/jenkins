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
    local command="${1:?}"
    local command_args=("${@:2}")

    mkdir -p "$STDCI_DATA_DIR"

    cmd_$command "${command_args[@]}"
}

cmd_deploy_all() {
    local jenkins_server="${1:?ERROR: You have to specify jenkins server url}"
    shift
    local secrets=("${@}");
    local arg_count=${#@}

    local hostname; hostname="$(hostname)"
    local base_cmd container_name extras
    for secret in "${secrets[@]}"; do
        cmd_deploy_slot "$arg_count" "$jenkins_server" "$secret"
        (( --arg_count ))
    done
}

cmd_deploy_slot() {
    local slot_id="${1:?ERROR. You must provide slot ID}"
    local jenkins_server="${2:?ERROR: You have to specify jenkins server url}"
    local secret="${3:?ERROR. You must provide a secret}"

    cmd_verify_slot_free "$slot_id" || return 1

    local extras; IFS=" " read -r -a extras <<< \
        "$(prep_slave_slot "$slot_id" "$secret")"

    local container_name="$(get_container_name "$slot_id")"
    base_cmd=(
        --privileged "--name=$container_name" -d
        -e "STDCI_SLAVE_CONTAINER_NAME=$container_name"
        -e "JENKINS_URL=$jenkins_server"
        -e "JENKINS_AGENT_NAME=$container_name"
        -e "JENKINS_SECRET=$secret"
        -e "CI_RUNTIME_UNAME=$RUNTIME_USERNAME"
    )

    docker run "${base_cmd[@]}" "${extras[@]}" "$STDCI_IMAGE_NAME"
}

cmd_verify_slot_free() {
    local slot_id="${1:?ERROR. You must provide slot ID}"
    local container_name="$(get_container_name "$slot_id")"
    local container_id="$(
        docker ps --filter="name=$container_name" --format="{{.ID}}"
    )"
    if [[ -n "$container_id" ]]; then
        local answer
        echo "There is a running container on slot $slot_id."
        printf "Do you want to remove it? [y/N]? "
        read -r answer
        if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
            echo "Trying to remove: $container_name ($container_id)"
            docker rm "$container_id" || {
                echo "Failed to remove the container"
                return 1
            }
        else
            echo "Slot is already in use by $container_name ($container_id)"
            return 1
        fi
    fi
    echo "Slot $slot_id is free"
}

prep_slave_slot() {
    local slave_count="${1:?}"
    local slave_home="${STDCI_DATA_DIR}/container-slaves/${slave_count}"

    mkdir -p "$slave_home"

    local cmd
    cmd+=( "$(prep_runtime_user_home "$slave_home")" )
    cmd+=( "$(prep_lago_dirs "$slave_home")" )
    cmd+=( "$(prep_mock_dirs "$slave_home")" )
    cmd+=( "$(prep_docker_dirs "$slave_home")" )

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
    local mock_cache="${slave_home}/var/cache/mock"
    local mock_lib="${slave_home}/var/lib/mock"

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

prep_docker_dirs() {
    local slave_home="${1:?}"
    local docker_home="${slave_home}/var/lib/docker"

    mkdir -p "$docker_home"
    local cmd real_docker_home
    real_docker_home="$(realpath "$docker_home")"
    cmd=(
        -v "$real_docker_home:/var/lib/docker"
    )
    printf "%s " "${cmd[@]}"
}

get_container_name() {
    local slot_id="${1:?ERROR. You must provide splot ID}"
    local hostname="$(hostname)"
    local container_name="${hostname}-container-${slot_id}"
    echo "$container_name"
}

main "$@"
