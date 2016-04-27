#!/bin/bash -xe
echo 'shell_scripts/system_tests.collect_logs.sh'

#
# Required jjb vars:
#    version
#
VERSION={version}
SUITE_TYPE={suite_type}

WORKSPACE="$PWD"
OVIRT_SUITE="$SUITE_TYPE_suite_$VERSION"
TESTS_LOGS="$WORKSPACE/ovirt-system-tests/exported-artifacts"

rm -rf "$WORKSPACE/exported-artifacts"
mkdir -p "$WORKSPACE/exported-artifacts"

if [[ -d "$TESTS_LOGS" ]]; then
    mv "$TESTS_LOGS/"* "$WORKSPACE/exported-artifacts/"
fi
