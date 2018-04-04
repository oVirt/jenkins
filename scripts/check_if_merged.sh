#!/bin/bash -e
echo "scritps/check_if_merged.sh"
#
# Check if a change pointed by GERRIT_REFSPEC is merged
#
GERRIT_PROJECT="${GERRIT_PROJECT:?Error GERRIT_PROJECT is unset.}"
CLONE_DIR_NAME="${CLONE_DIR_NAME}"
GERRIT_BRANCH="${GERRIT_BRANCH:?Error GERRIT_BRANCH is unset.}"
GERRIT_REFSPEC="${GERRIT_REFSPEC:?Error GERRIT_REFSPEC is unset.}"
GERRIT_NAME="${GERRIT_NAME:?Error GERRIT_NAME is unset.}"

main() {
    local workspace
    if [[ ! "${WORKSPACE}" ]]; then
        trap 'clean "$workspace"' EXIT HUP INT QUIT
        workspace="$(mktemp -d --tmpdir stdci_check_is_merged.XXXXX)"
    else
        workspace="${WORKSPACE}"
    fi

    if [[ -z "$CLONE_DIR_NAME" ]]; then
        local clone_dir_name="${GERRIT_PROJECT##*/}"
    else
        local clone_dir_name="$CLONE_DIR_NAME"
    fi
    local path_to_project="${workspace}/${clone_dir_name}"
    git init "$path_to_project"
    (
        cd "$path_to_project"
        local clone_url="https://${GERRIT_NAME}/${GERRIT_PROJECT}"
        git fetch "$clone_url" "+refs/heads/${GERRIT_BRANCH}:__the-branch__"
        git fetch "$clone_url" "+${GERRIT_REFSPEC}:__the-patch__"

        local merge_base="$(git merge-base __the-branch__ __the-patch__)"
        local patch_to_cmp="$(git rev-parse __the-patch__)"
        if [[ "$merge_base" == "$patch_to_cmp" ]]; then
            echo "$GERRIT_REFSPEC is merged"
            return 0
        fi
        echo "$GERRIT_REFSPEC is not merged"
        return 1
    )
}

clean() {
    local tmpdir="${1:?Error. Temp dir must be provided}"
    rm -rf "$tmpdir"
}

main
