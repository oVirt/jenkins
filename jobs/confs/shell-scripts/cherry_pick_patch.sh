#!/bin/bash -xe
echo "shell-scripts/cherry_pick_patch.sh"
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# patch
#     patch to be cherry picked

project="{project}"
patch="{patch}"
WORKSPACE=$PWD

# go to the source directory
pushd "$WORKSPACE/$project"
# make sure it's properly clean
git clean -dxf
# cherry pick the patch
git fetch git://gerrit.ovirt.org/$project $patch && git cherry-pick FETCH_HEAD
