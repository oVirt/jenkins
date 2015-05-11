#!/bin/bash -xe
echo "shell-scripts/jenkins_cleanup_yaml.sh"
## LIST REMOVED JOBS FROM YAML SINCE LAST COMMIT
new_xmls_dir="$WORKSPACE/new_xmls"
old_xmls_dir="$WORKSPACE/old_xmls"
confs_dir="${WORKSPACE}/jenkins/jobs/confs/"
yaml_dir="${confs_dir}/yaml"
conf_file="${HOME}/.jenkinsjobsrc"
## cleanup
for dir in "$new_xmls_dir" "$old_xmls_dir"; do
    rm -rf "$dir"
    mkdir -p "$dir"
done
## Get new xmls
echo "Generating new xmls"
pushd "$confs_dir"
jenkins-jobs \
    --allow-empty \
    -l debug \
    --conf "$conf_file" \
    test \
        --recursive \
        -o "$new_xmls_dir" \
        "$yaml_dir"
echo "########################"
## Get old xmls
echo "Generating previous xmls"
cd "$WORKSPACE/jenkins"
git checkout HEAD^
if ! [[ -d "$confs_dir" ]]; then
    echo "  No previous config"
else
    pushd "$confs_dir"
    jenkins-jobs \
        --allow-empty \
        -l debug \
        --conf "$conf_file" \
        test \
            --recursive \
            -o "$old_xmls_dir" \
            "$yaml_dir"
    echo "########################"
    ## Get the diff
    xml_diff=$( diff -q "$old_xmls_dir" "$new_xmls_dir" | grep "Only in $old_xmls_dir" | awk '{ print $4 }' )
    echo "${xml_diff[@]}" > xml_diff.txt
fi
