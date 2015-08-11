#!/bin/bash -xe
echo "shell-scripts/jenkins_cleanup_yaml.sh"
## LIST REMOVED JOBS FROM YAML SINCE LAST COMMIT
new_xmls_dir="$WORKSPACE/new_xmls"
old_xmls_dir="$WORKSPACE/old_xmls"
confs_dir="${WORKSPACE}/jenkins/jobs/confs"
yaml_dir="${confs_dir}/yaml"
conf_file="${HOME}/.jenkinsjobsrc"
out_file="$WORKSPACE/xml_diff.txt"
## cleanup
for dir in "$new_xmls_dir" "$old_xmls_dir"; do
    [[ -d "$dir" ]] && rm -rf "$dir"
    mkdir -p "$dir"
done
## Get new xmls
echo "Generating new xmls"
pushd "$confs_dir"
# Needed for that commit where we check old dir structure vs new
[[ -d "${confs_dir}/projects" ]] \
&& yaml_dir_extended="$yaml_dir:${confs_dir}/projects" \
|| yaml_dir_extended="$yaml_dir"
jenkins-jobs \
    --allow-empty \
    -l debug \
    --conf "$conf_file" \
    test \
        --recursive \
        -o "$new_xmls_dir" \
        "$yaml_dir_extended"
echo "########################"
## Get old xmls
echo "Generating previous xmls"
cd "$WORKSPACE/jenkins"
git fetch origin
git reset --hard HEAD^1
if ! [[ -d "$confs_dir" ]]; then
    echo "  No previous config"
else
    pushd "$confs_dir"
    # Needed for that commit where we check old dir structure vs new
    [[ -d "${confs_dir}/projects" ]] \
    && yaml_dir_extended="$yaml_dir:${confs_dir}/projects" \
    || yaml_dir_extended="$yaml_dir"
    jenkins-jobs \
        --allow-empty \
        -l debug \
        --conf "$conf_file" \
        test \
            --recursive \
            -o "$old_xmls_dir" \
            "$yaml_dir_extended"
    echo "########################"
    ## Get the diff
    git reset --hard $GERRIT_PATCHSET_REVISION
    changed=false
    diff -q "$old_xmls_dir" "$new_xmls_dir" \
    | grep "Only in $old_xmls_dir" \
    | awk '{ print $4 }' \
    > "$out_file"
fi

echo "--------------------"
echo "Jobs that were deleted"
echo "--------------------"
cat "$out_file"
echo "--------------------"
