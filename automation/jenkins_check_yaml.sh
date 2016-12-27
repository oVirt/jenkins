#!/bin/bash -xe
echo "shell-scripts/jenkins_check_yaml.sh"
## assign branch to patch
branch_name=$(date +%s)
git branch $branch_name
cwd=`pwd`
## UPDATE JOBS FROM YAML
new_xmls_dir="$cwd/new_xmls"
old_xmls_dir="$cwd/old_xmls"
confs_dir="$cwd/jobs/confs"
yaml_dir="${confs_dir}/yaml"
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
    test \
        --recursive \
        -o "$new_xmls_dir" \
        "$yaml_dir_extended"
echo "########################"
## Get old xmls
echo "Generating previous xmls"
cd "$cwd"
git fetch origin
git reset --hard origin/master
if ! [[ -d "$confs_dir" ]]; then
    echo "  No previous config"
    exit 1
fi
pushd "$confs_dir"
# Needed for that commit where we check old dir structure vs new
[[ -d "${confs_dir}/projects" ]] \
&& yaml_dir_extended="$yaml_dir:${confs_dir}/projects" \
|| yaml_dir_extended="$yaml_dir"
jenkins-jobs \
    --allow-empty \
    -l debug \
    test \
        --recursive \
        -o "$old_xmls_dir" \
        "$yaml_dir_extended"
echo "########################"
## Get the diff
git reset --hard $GERRIT_PATCHSET_REVISION
changed=false
mkdir -p "$cwd/exported-artifacts"
diff -u "$old_xmls_dir" "$new_xmls_dir" \
| "$cwd/jobs/confs/shell-scripts/htmldiff.sh" \
> "$cwd/exported-artifacts/differences.html" \
|| changed=true

if $changed; then
    echo "WARNING: #### XML CHANGED ####"
    echo "Changed files:"
    diff -q "$old_xmls_dir" "$new_xmls_dir" | awk '{ print $2 }' || :
fi
## return to patch
git checkout $branch_name
