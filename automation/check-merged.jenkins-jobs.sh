#!/bin/bash -ex
# check-merged.jenkins-jobs.sh - Deploy jobs when patches are merged

JJB_PROJECTS_FOLDER="${JJB_PROJECTS_FOLDER:?must be defined in Jenkins instance}"
JENKINS_URL="${JENKINS_URL:?must be provided in secrets file}"
(
    # Avoid dumping credentials to STDERR
    set +x
    JENKINS_USER="${JENKINS_USER:?must be provided in secrets file}"
    JENKINS_PASSWORD="${JENKINS_PASSWORD:?must be provided in secrets file}"
)

# We're just gonna assume this script runs when $PWD is the project root since
# its essentially meant to be triggered by STDCI
source scripts/jjb_diff.sh
source automation/stdci_venv.sh

main() {
    local old_jobs_cache
    local jobs_cache
    local success=1

    export XDG_CACHE_HOME="$(mktemp -d xdg_cache_home_override_XXXXX --tmpdir)"
    old_jobs_cache="$(mktemp old_jobs_cahce.XXXXX.yml --tmpdir)"
    jobs_cache="jenkins_jobs/cache-host-jobs-${JENKINS_URL//[:\/.]/_}.yml"
    jobs_cache="$XDG_CACHE_HOME/$jobs_cache"

    stdci_venv::activate "$0"

    mk_old_jobs_cache > "$old_jobs_cache" \
    && cp -f "$old_jobs_cache" "$jobs_cache" \
    && deploy_jobs \
    && cleanup_deleted_jobs "$old_jobs_cache" \
    && success=0

    rm -f "$old_jobs_cache"
    rm -rf "$XDG_CACHE_HOME"
    return $success
}

mk_old_jobs_cache() {
    mk_jobs_cache generate_old_xmls
}

mk_new_jobs_cache() {
    mk_jobs_cache generate_new_xmls
}

mk_jobs_cache() {
    local generate_xml_cmd="${1:?}"
    local jobs_xml_dir
    local success=1

    jobs_xml_dir="$(mktemp -d job_xmls_XXX --tmpdir)" \
    && $generate_xml_cmd "$jobs_xml_dir" "jobs/confs" "$PWD" \
    && (
        cd "$jobs_xml_dir"
        find . -type f -printf '%P\0' \
        | xargs -0 -r md5sum \
        | sed -re "s/\/config.xml\$//;s/'/''/;s/^([0-9a-f]+)  (.+)\$/'\2': \1/"
    ) && success=0
    rm -rf "$jobs_xml_dir"
    return $success
}

deploy_jobs() {
    (
        cd "jobs/confs"
        run_jjb update \
            --workers 0 \
            --recursive \
            "yaml:$JJB_PROJECTS_FOLDER"
    )
}

cleanup_deleted_jobs() {
    local old_jobs_cache="${1:?}"
    local deleted_jobs

    deleted_jobs=($(get_deleted_jobs "$old_jobs_cache"))
    if [[ ${#deleted_jobs[@]} -le 0 ]]; then
        echo "No jobs were deleted"
        return
    fi
    echo "${#deleted_jobs[@]} jobs were deleted:"
    printf "  - %s\n" "${deleted_jobs[@]}"
    run_jjb delete "${deleted_jobs[@]}"
}

get_deleted_jobs() {
    local old_jobs_cache="${1:?}"
    local new_jobs_cache
    local jobs_cache
    local success=1

    new_jobs_cache="$(mktemp new_jobs_cahce.XXXXX.yml --tmpdir)" \
    && mk_new_jobs_cache > "$new_jobs_cache" \
    && cat "$old_jobs_cache" - <<<--- "$new_jobs_cache" \
        | python -c "$(printf '%s\n' \
            'import yaml' \
            'import sys' \
            'job_caches = yaml.load_all(sys.stdin)' \
            'deleted = set.difference(*(set(c.keys()) for c in job_caches))' \
            'print("".join(d + "\n" for d in deleted))'
        )"
    rm -f "$new_jobs_cache"
    return $success
}

run_jjb() {
    local conf_file success=1
    conf_file="$(mktemp -t .jenkinsjobsrc.XXXXX)"
    get_jjb_conf_file > "$conf_file"
    jenkins-jobs \
        --allow-empty \
        --conf "$conf_file" \
        "$@" \
    && success=0
    rm -f "$conf_file"
    return $success
}

get_jjb_conf_file() {
    (
        # Avoid dumping configuration to STDERR
        set +x
        echo "[jenkins]"
        echo "user=$JENKINS_USER"
        echo "password=$JENKINS_PASSWORD"
        echo "url=$JENKINS_URL"
        echo
        echo "[job_builder]"
        echo "keep_descriptions=True"
        echo "recursive=True"
        echo "allow_empty_variables=True"
        echo "allow_empty=True"
    )
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
