#!/bin/bash -ex
echo "shell-scripts/collect_artifacts.sh"
cat <<EOC
_______________________________________________________________________
#######################################################################
#                                                                     #
#                         ARTIFACT COLLECTION                         #
#                                                                     #
#######################################################################
EOC

# Injected by the standard-stage template
PROJECT="${PROJECT:?}"
WORKSPACE="${WORKSPACE:-$PWD}"
EXPORTED_ARTIFACTS="$WORKSPACE/exported-artifacts"
# Images tagged with this tag will be exported
CONTAINER_IMAGES_EXPORT_TAG="exported-artifacts"
# If the credentials are not set (provided by Jenkins), exit with error
CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME="${CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME:?}"
CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD="${CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD:?}"
# Provided by Jenkins too, if unset then exit with error
INTERMEDIATE_CONTAINER_IMAGES_REPO="${INTERMEDIATE_CONTAINER_IMAGES_REPO:?}"
ATTEMPTS_TO_PUSH_IMAGE=3
DELAY_BETWEEN_ATTEMPTS=1
PUSHED_IMAGES_FILE="$EXPORTED_ARTIFACTS/pushed_container_images.lst"
PUSHED_IMAGE_HTML_FILE="$EXPORTED_ARTIFACTS/pushed_containers_details.html"


main(){
    mkdir -p "$EXPORTED_ARTIFACTS"
    export_docker_images
    export_all_artifacts
    createrepo_if_needed
}


cleanup(){
    # Logout from docker
    sudo docker logout > /dev/null 2>&1
}

push_image(){
    local image_to_push="${1:?}"
    local attempts

    for (( attempts = $ATTEMPTS_TO_PUSH_IMAGE; attempts > 0; --attempts )){
        echo "Pushing image: $image_to_push"
        if sudo docker push $image_to_push; then
            echo "Image pushed successfully"
            echo "$image_to_push" > "$PUSHED_IMAGES_FILE"
            return 0
        fi

        echo "Push failed. Sleeping $DELAY_BETWEEN_ATTEMPTS sec and retrying."
        echo "Attempts left: $attempts"
        sleep $DELAY_BETWEEN_ATTEMPTS
    }

    return 1
}

gen_html_details_file(){
    local image_id="${1:?}"
    local image_tag="${2:?}"
    local dest_repo="${3:?}"
    local img_details="${4:?}"

    echo "
        <table style=\"width: 840px;\">
        <tbody>
            <tr style=\"height: 23px;\">
            <td style=\"width: 136px; height: 23px;\">
              <b>Image ID:</b></td>
              <td style=\"width: 703px; height: 23px;\">
                <pre>${image_id}</pre>
              </td></tr>
            <tr style=\"height: 23px;\">
            <td style=\"width: 136px; height: 23px;\">
              <b>Image TAG:</b></td>
              <td style=\"width: 703px; height: 23px;\">
                <pre>${image_tag}</pre>
              </td></tr>
            <tr style=\"height: 23px;\">
              <td style=\"width: 136px; height: 23px;\">
              <b>Repository:</b></td>
              <td style=\"width: 703px; height: 23px;\">
                <pre>${dest_repo}</pre>
              </td></tr>
            <tr style=\"height: 23px;\">
              <td style=\"width: 136px; height: 23px;\">
              <b>Run command:</b></td>
              <td style=\"width: 703px; height: 23px;\">
                <pre>docker run ${img_details}</pre>
              </td></tr>
            <tr style=\"height: 3.5px;\">
              <td style=\"width: 136px; height: 3.5px;\">
              <b>Pull command:</b></td>
              <td style=\"width: 703px; height: 3.5px;\">
                <pre>docker pull ${img_details}</pre>
              </td></tr>
        </tbody>
        </table>
    "
}

export_docker_images(){
    local build_url_sha1 \
        docker_images_to_tag \
        tagged_image_str \
        containers_repo

    # We re-tag every exported image to give it a unique name
    build_url_sha1="$(sha1sum <<< "$BUILD_URL")"
    build_url_sha1="${build_url_sha1%% *}"

    # Find the images we need to push
    docker_images_to_tag=$(
        sudo docker images --format="{{.Repository}}:{{.Tag}}" | \
            grep -oP ".+?(?=:$CONTAINER_IMAGES_EXPORT_TAG)"
    ) ||:
    [[ -z "$docker_images_to_tag" ]] && return 0

    sudo docker login \
        -u="$CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME" \
        -p="$CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD"
    containers_repo="${INTERMEDIATE_CONTAINER_IMAGES_REPO}"
    # Loop through the images we want to export and push them to registery
    for image in $docker_images_to_tag; do
        tagged_image_str="${containers_repo}${image}:${build_url_sha1}"
        sudo docker tag "$image:$CONTAINER_IMAGES_EXPORT_TAG" \
            "$tagged_image_str"
        push_image "$tagged_image_str" || return 1
        gen_html_details_file "$image" \
            "$build_url_sha1" \
            "$containers_repo" \
            "$tagged_image_str" >> "$PUSHED_IMAGE_HTML_FILE"
    done
    return 0
}


export_all_artifacts(){
    # Move the exported artifacts to jenkins workspace, as they are created in
    # the project root
    if ls "$WORKSPACE/$PROJECT/exported-artifacts/"* &>/dev/null; then
        sudo mv "$WORKSPACE/$PROJECT/exported-artifacts/"* "$EXPORTED_ARTIFACTS"
        sudo rmdir "$WORKSPACE/$PROJECT/exported-artifacts/"
    fi
    sudo chown -R "$USER:$USER" "$EXPORTED_ARTIFACTS"
}


createrepo_if_needed(){
    if [[ ! -e "$EXPORTED_ARTIFACTS/repodata" ]] &&
        find "$EXPORTED_ARTIFACTS" -type f -name '*.rpm' | grep -q .
    then
        if [[ -e '/usr/bin/dnf' ]]; then
            sudo dnf install -y createrepo
        else
            sudo yum install -y createrepo
        fi
        createrepo "$EXPORTED_ARTIFACTS"
    fi
}


trap cleanup INT HUP
main

exit 0
