#!/bin/bash -xe
echo "shell-scripts/jenkins_check_yaml.sh"

JJB_PROJECTS_FOLDER="${JJB_PROJECTS_FOLDER:?must be defined in Jenkins instance}"

# We're just gonna assume this script runs when $PWD is the project root since
# its essentially meant to be triggered by STDCI
source scripts/jjb_diff.sh
source automation/stdci_venv.sh

check_deleted_publisher_jobs() {
    local new_xmls_dir="${1:?}"

    python automation/check_publishers_not_deleted.py "$new_xmls_dir"
}

diff_old_with_new() {
    local project_folder="${1:?}"
    local old_xmls_dir="${2:?}"
    local new_xmls_dir="${3:?}"

    changed=false
    mkdir -p "$project_folder/exported-artifacts"
    diff --recursive -u "$old_xmls_dir" "$new_xmls_dir" \
    | "$project_folder/jobs/confs/shell-scripts/htmldiff.sh" \
    > "$project_folder/exported-artifacts/differences.html" \
    && changed=true

    if $changed; then
        echo "WARNING: #### XML CHANGED ####"
        echo "Changed files:"
        diff --recursive -q "$old_xmls_dir" "$new_xmls_dir" \
            | awk '{ print $2 }' \
            || :
    fi
}

main() {
    local project_folder="$(pwd)"
    local new_xmls_dir="$(mktemp -d new_xmls_XXX --tmpdir)"
    local old_xmls_dir="$(mktemp -d old_xmls_XXX --tmpdir)"
    local confs_dir="jobs/confs"

    stdci_venv::activate "$0"

    generate_new_xmls "$new_xmls_dir" "$confs_dir"
    check_deleted_publisher_jobs "$new_xmls_dir"
    generate_old_xmls "$old_xmls_dir" "$confs_dir" "$project_folder"
    diff_old_with_new "$project_folder" "$old_xmls_dir" "$new_xmls_dir"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
