#!/bin/bash -xe
echo "shell-scripts/system_tests.sh"

#
# Required jjb vars:
#    version
#
VERSION={version}

WORKSPACE="$PWD"
OVIRT_SUITE="basic_suite_$VERSION"
PREFIX="$WORKSPACE/ovirt-system-tests/deployment-$OVIRT_SUITE"

chmod g+x "$WORKSPACE"
# make sure there's no prefix or lago will fail
rm -rf "$PREFIX"

cd ovirt-system-tests
../jenkins/mock_configs/mock_runner.sh \
    --mock-confs-dir ../jenkins/mock_configs \
    --try-proxy \
    --execute-script "automation/$OVIRT_SUITE.sh" \
    fc22
