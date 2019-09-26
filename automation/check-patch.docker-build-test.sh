#!/bin/bash -xe

main() {
    test_docker_container
}

test_docker_container() {
    # Build a dummy container and run it
    # we also tag it with exported-artifacts to test the export
    local export_tag="exported-artifacts"
    docker build -t check_patch_container:$export_tag data/Dockerfiles/
    docker run check_patch_container:$export_tag
}


if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
