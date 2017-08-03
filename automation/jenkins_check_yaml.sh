#!/bin/bash -xe
echo "shell-scripts/jenkins_check_yaml.sh"

source automation/parameters.sh

JJB_PROJECTS_DIR="${JJB_PROJECTS_DIR:?This environment variable has to be defined }"

US_SRC_COLLECTOR="python-scripts/upstream-source-collector.py"

generate_jobs_xml() {
    local confs_dir="${1:?}"
    local xmls_output_dir="${2:?}"

    (
        cd "$confs_dir"
        jenkins-jobs \
            --allow-empty \
            test \
                --recursive \
                -o "$xmls_output_dir" \
                "yaml:$JJB_PROJECTS_DIR"
    )
}

generate_new_xmls() {
    local new_xmls_dir="${1:?}"
    local confs_dir="${2:?}"

    generate_jobs_xml "$confs_dir" "$new_xmls_dir"
}

check_deleted_publisher_jobs() {
    local new_xmls_dir="${1:?}"

    python automation/check_publishers_not_deleted.py "$new_xmls_dir"
}

generate_old_xmls() {
    local old_xmls_dir="${1:?}"
    local confs_dir="${2:?}"
    local project_folder="${3:?}"
    local old_project_ws="$(mktemp -d)"
    local old_confs_dir="$old_project_ws/jenkins/$confs_dir"
    local us_sources_location="${project_folder%/*}"
    local branch_name=$(date +%s)

    git branch $branch_name HEAD^
    (
        cd "$old_project_ws"
        git clone --branch $branch_name --reference "$project_folder/.git" \
            "file:///$project_folder" jenkins
        python "$project_folder/$confs_dir/$US_SRC_COLLECTOR" --usdir "$us_sources_location"
        cd jenkins
        if ! [[ -d "$confs_dir" ]]; then
            echo "  No previous config"
            exit 1
        fi
        # Needed for that commit where we check old dir structure vs new
        generate_jobs_xml "$confs_dir" "$old_xmls_dir"
    )
}

diff_old_with_new() {
    local project_folder="${1:?}"
    local old_xmls_dir="${2:?}"
    local new_xmls_dir="${3:?}"

    changed=false
    mkdir -p "$project_folder/exported-artifacts"
    diff -u "$old_xmls_dir" "$new_xmls_dir" \
    | "$project_folder/jobs/confs/shell-scripts/htmldiff.sh" \
    > "$project_folder/exported-artifacts/differences.html" \
    || changed=true

    if $changed; then
        echo "WARNING: #### XML CHANGED ####"
        echo "Changed files:"
        diff -q "$old_xmls_dir" "$new_xmls_dir" | awk '{ print $2 }' || :
    fi
}

main() {
    local project_folder="$(pwd)"
    local new_xmls_dir="$(mktemp -d)"
    local old_xmls_dir="$(mktemp -d)"
    local confs_dir="jobs/confs"

    generate_new_xmls "$new_xmls_dir" "$confs_dir"
    check_deleted_publisher_jobs "$new_xmls_dir"
    generate_old_xmls "$old_xmls_dir" "$confs_dir" "$project_folder"
    diff_old_with_new "$project_folder" "$old_xmls_dir" "$new_xmls_dir"
}

main
