#!/bin/bash -e

JJB_PROJECTS_FOLDER="${JJB_PROJECTS_FOLDER:?must be defined in Jenkins instance}"

source scripts/mk_refspec_include.sh

run_jjb() {
    mk_refspec_include
    jenkins-jobs --allow-empty "$@"
}

generate_jobs_xml() {
    local confs_dir="${1:?}"
    local xmls_output_dir="${2:?}"

    (
        cd "$confs_dir"
        run_jjb test \
            --recursive \
            --config-xml \
            -o "$xmls_output_dir" \
            "yaml:$JJB_PROJECTS_FOLDER"
    )
}

generate_new_xmls() {
    local new_xmls_dir="${1:?}"
    local confs_dir="${2:?}"

    generate_jobs_xml "$confs_dir" "$new_xmls_dir"
}

generate_old_xmls() {
    local old_xmls_dir="${1:?}"
    local confs_dir="${2:?}"
    local project_folder="${3:?}"
    local old_project_ws
    local branch_name=$(date +%s)
    local result=1

    git branch $branch_name HEAD^
    (
        old_project_ws="$(mktemp -d)" \
        && cd "$old_project_ws" \
        && git clone -q \
            --branch $branch_name --reference "$project_folder/.git" \
            "file:///$project_folder" jenkins \
        && cd jenkins \
        && usrc -v get \
        && (
            [[ ! -d "$confs_dir" ]] \
            || generate_jobs_xml "$confs_dir" "$old_xmls_dir"
        ) \
        && rm -rf "$old_project_ws"
    ) && result=0
    git branch -q -D $branch_name
    return $result
}

jjb_diff() {
    local project_folder="$(pwd)"
    local new_xmls_dir="$(mktemp -d new_xmls_XXX --tmpdir)"
    local old_xmls_dir="$(mktemp -d old_xmls_XXX --tmpdir)"
    local confs_dir="jobs/confs"

    generate_new_xmls "$new_xmls_dir" "$confs_dir"
    generate_old_xmls "$old_xmls_dir" "$confs_dir" "$project_folder"
    diff --recursive "$@" "$old_xmls_dir" "$new_xmls_dir"
}

main() {
    jjb_diff "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
