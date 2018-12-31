#!/bin/bash -xe

main() {
    local substage_name stage_name
    stage_name="$(basename "$0")"
    stage_name="${stage_name%%.*}"
    substage_name="$(basename "$0" | cut -d . -f 2)"

    local image_tag=testing
    if [[ "$stage_name" = build-artifacts ]]; then
        image_tag=exported-artifacts
    fi

    build_image "$substage_name" "$image_tag"
    "verify_${substage_name//-/_}" "$substage_name" "$image_tag"
}

build_image() {
    local image_to_build="${1:?}"
    local tag="${2:-testing}"

    (
        cd container/"${image_to_build}"
        docker build -t "${image_to_build}":"${tag}" .
    )
}

verify_el7_loader_node() {
    local image="${1:?}"
    local tag="${2:?}"
    local jenkins_repo="https://gerrit.ovirt.org/jenkins"

    docker run -i --rm "${image}:${tag}" bash -c "
        git clone $jenkins_repo
        cd jenkins
        ./scripts/usrc.py get
    "
}

verify_el7_runner_node() {
    # Just a placeholder for now...
    return
}

main "$@"
