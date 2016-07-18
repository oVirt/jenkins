#!/bin/bash -xe
echo "shell-scripts/build-artifacts-manual_any.sh"

# handle tarball
rm -Rf "${{WORKSPACE}}"/exported-artifacts
mkdir -p "${{WORKSPACE}}"/exported-artifacts
env
mv TARBALL_FILE "${{WORKSPACE}}"/exported-artifacts/"${{TARBALL_FILE}}"
