#!/bin/bash -xe
echo 'shell_scripts/system_tests.cleanup.sh'

#
# Required jjb vars:
#    version
#
VERSION={version}

WORKSPACE=$PWD

cd "$WORKSPACE/ovirt-system-tests/"
./run_suite.sh --cleanup "basic_suite_$VERSION"
