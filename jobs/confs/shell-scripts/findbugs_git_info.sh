#!/bin/bash
echo "shell-scripts/findbugs_git_info.sh"

# Show extra information about the code being built
echo "######################################################"
cd ovirt-engine
git log -1
echo "######################################################"
git status
echo "######################################################"