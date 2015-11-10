#!/bin/bash -ex
echo "shell-scripts/jenkins_deploy_yamls.sh"
## UPDATE JOBS FROM YAML
#
# Requires the env vars:
#   FLUSH_CACHE
#     If set to 'true' will force updating the jobs and ignore the cache
#
WORKSPACE=$PWD
FLUSH_CACHE="${FLUSH_CACHE:-false}"

confs_dir="${WORKSPACE}/jenkins/jobs/confs"
yaml_dir="${confs_dir}/yaml:${confs_dir}/projects"
conf_file="${HOME}/.jenkinsjobsrc"
options=()
### Flush the cache if specified
if [[ "$FLUSH_CACHE" == "true" ]]; then
    options+=("--flush-cache")
fi
cd "$confs_dir"
[[ -d "${confs_dir}/projects" ]] \
&& yaml_dir_extended="$yaml_dir:${confs_dir}/projects" \
|| yaml_dir_extended="$yaml_dir"
jenkins-jobs \
    -l debug \
    --allow-empty \
    --conf "$conf_file" \
    "${options[@]}" \
    update \
        --workers 0 \
        "$yaml_dir_extended"
