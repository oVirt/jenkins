#!/bin/bash -xe
# shell-scripts/build_local_srcrpm_releng.sh
# PARAMETERS
#
# subproject
#     Name of the subproject it runs on, specifically the dir where the code
#     has been cloned
#
# extra-build-options
#     extra options to pass to the build.sh script
#
# env
#     extra env variables to set when building

subproject="{subproject}"
extra_build_options=({extra-build-options})
extra_env="{env}"
WORKSPACE=$PWD

# Build the src_rpms
# Get the release suffix
pushd "$WORKSPACE/releng-tools/specs/$subproject"
# make sure it's properly clean
git clean -dxf
# build srcrpm
./build.sh "${{extra_build_options[@]}}"
mv *src.rpm exported-artifacts/
