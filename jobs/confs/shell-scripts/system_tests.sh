#!/bin/bash -xe
echo "shell-scripts/system_tests.sh"

#
# Required jjb vars:
#    version
#
VERSION={version}
SUITE_TYPE={suite_type}

WORKSPACE="$PWD"
GIT_SUBDIR="ovirt-system-tests"
OVIRT_SUITE="${{SUITE_TYPE}}_suite_$VERSION"
PREFIX="$WORKSPACE/$GIT_SUBDIR/deployment-$OVIRT_SUITE"
OVIRT_SUITE_DIR="$GIT_SUBDIR/${{SUITE_TYPE}}-suite-$VERSION"

## update extra source if we got it as param ###
if ! [ -z ${{CUSTOM_REPOS+x}} ]; then
    echo "$CUSTOM_REPOS" > $WORKSPACE/$OVIRT_SUITE_DIR/extra_sources
fi

chmod g+x "$WORKSPACE"
# make sure there's no prefix or lago will fail
rm -rf "$PREFIX"

cd ovirt-system-tests
../jenkins/mock_configs/mock_runner.sh \
    --mock-confs-dir ../jenkins/mock_configs \
    --try-proxy \
    --execute-script "automation/$OVIRT_SUITE.sh" \
    {chroot_distro}
