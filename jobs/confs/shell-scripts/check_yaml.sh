#!/bin/bash -e
## UPDATE JOBS FROM YAML
new_xmls_dir="$WORKSPACE/new_xmls"
old_xmls_dir="$WORKSPACE/old_xmls"
confs_dir="${WORKSPACE}/jenkins/jobs/confs/"
yaml_dir="${confs_dir}/yaml"
conf_file="${HOME}/.jenkinsjobsrc"
## cleanup
for dir in "$new_xmls_dir" "$old_xmls_dir"; do
    [[ -d "$dir" ]] && rm -rf "$dir"
    mkdir -p "$dir"
done
## Get new xmls
echo "Generating new xmls"
pushd "$confs_dir"
jenkins-jobs --conf "$conf_file" $options test -o "$new_xmls_dir" "$yaml_dir"
echo "########################"
## Get old xmls
echo "Generating previous xmls"
cd "$WORKSPACE/jenkins"
git fetch origin
git reset --hard origin/master
if ! [[ -d "$confs_dir" ]]; then
    echo "  No previous config"
else
    pushd "$confs_dir"
    jenkins-jobs --conf "$conf_file" $options test -o "$old_xmls_dir" "$yaml_dir"
    echo "########################"
    ## Get the diff
    git reset --hard $GERRIT_REFSPEC
    changed=false
    diff -u "$old_xmls_dir" "$new_xmls_dir" \
	| "$WORKSPACE/jenkins/jobs/confs/shell-scripts/htmldiff.sh" \
	> "$WORKSPACE/differences.html" \
    || changed=true

    if $changed; then
	echo "WARNING: #### XML CHANGED ####"
	echo "Changed files:"
	diff -q "$old_xmls_dir" "$new_xmls_dir" | awk '{ print $2 }' || :
    fi
fi
