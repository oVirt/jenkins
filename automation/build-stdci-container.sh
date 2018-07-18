#!/bin/bash -ex

LOCAL_IMAGE_NAME="local/stdci"
REMOTE_IMAGE_NAME="stdci-slave"

main() {
    build_image
    export_image
}

build_image()(
    cd container
    make
)

export_image() {
    docker tag "$LOCAL_IMAGE_NAME" "$REMOTE_IMAGE_NAME":exported-artifacts
}

main "$@"
