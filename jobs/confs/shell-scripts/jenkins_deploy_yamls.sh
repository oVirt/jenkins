#!/bin/bash -ex
echo "shell-scripts/jenkins_deploy_yamls.sh"
## UPDATE JOBS FROM YAML
confs_dir="${WORKSPACE}/jenkins/jobs/confs"
yaml_dir="${confs_dir}/yaml"
conf_file="${HOME}/.jenkinsjobsrc"
### Flush the cache if specified
if [[ "$FLUSH_CACHE" == "true" ]]; then
    options="$options  --flush-cache"
fi
cd "$confs_dir"
jenkins-jobs \
    -l debug \
    --allow-empty-variables \
    --workers 0 \
    --conf "$conf_file" \
    $options \
    update "$yaml_dir"
