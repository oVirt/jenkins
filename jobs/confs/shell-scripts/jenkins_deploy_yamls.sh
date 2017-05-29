#!/bin/bash -ex
echo "shell-scripts/jenkins_deploy_yamls.sh"
## UPDATE JOBS FROM YAML
#
# Requires the env vars:
#   FLUSH_CACHE
#     If set to 'true' will force updating the jobs and ignore the cache
#
#   JOBS_FILTERS
#     Comma separated globs to select which jobs to update, if not set will
#     select them all
#
WORKSPACE=$PWD
FLUSH_CACHE="${FLUSH_CACHE:-false}"
JOBS_FILTERS=(${JOBS_FILTERS:+${JOBS_FILTERS//,/ }})

# This parameter will be defined as a global parameterrameter for
# all jobs in Jenkins configuration
JJB_PROJECTS_FOLDER=${JJB_PROJECTS_FOLDER:?variable not set or empty}

confs_dir="${WORKSPACE}/jenkins/jobs/confs"
yaml_dir="${confs_dir}/yaml:${confs_dir}/${JJB_PROJECTS_FOLDER}"
conf_file="${HOME}/.jenkinsjobsrc"
options=()

### Flush the cache if specified
if [[ "$FLUSH_CACHE" == "true" ]]; then
    options+=("--flush-cache")
fi
cd "$confs_dir"
[[ -d "${confs_dir}/${JJB_PROJECTS_FOLDER}" ]] \
&& yaml_dir_extended="$yaml_dir:${confs_dir}/${JJB_PROJECTS_FOLDER}" \
|| yaml_dir_extended="$yaml_dir"
jenkins-jobs \
    -l debug \
    --allow-empty \
    --conf "$conf_file" \
    "${options[@]}" \
    update \
        --workers 0 \
        "$yaml_dir_extended" \
        "${JOBS_FILTERS[@]}"
