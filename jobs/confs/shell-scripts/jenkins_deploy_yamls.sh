#!/bin/bash -ex
echo "shell-scripts/jenkins_deploy_yamls.sh"
## UPDATE JOBS FROM YAML
confs_dir="${WORKSPACE}/jenkins/jobs/confs"
yaml_dir="${confs_dir}/yaml:${confs_dir}/projects"
conf_file="${HOME}/.jenkinsjobsrc"
### Flush the cache if specified
if [[ "$FLUSH_CACHE" == "true" ]]; then
    options="$options  --flush-cache"
fi
cd "$confs_dir"
[[ -d "${confs_dir}/projects" ]] \
&& yaml_dir_extended="$yaml_dir:${confs_dir}/projects" \
|| yaml_dir_extended="$yaml_dir"
jenkins-jobs \
    -l debug \
    --allow-empty \
    --conf "$conf_file" \
    $options \
    update \
        --workers 0 \
        "$yaml_dir_extended"
