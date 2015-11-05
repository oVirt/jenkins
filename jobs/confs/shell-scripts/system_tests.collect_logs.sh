#!/bin/bash -xe
echo 'shell_scripts/system_tests.collect_logs.sh'

#
# Required jjb vars:
#    version
#
VERSION={version}

WORKSPACE="$PWD"
OVIRT_SUITE="basic_suite_$VERSION"
PREFIX="$WORKSPACE/ovirt-system-tests/deployment-$OVIRT_SUITE"

mkdir -p "$WORKSPACE/exported-artifacts"

if [[ -d "$PREFIX" ]]; then

    if [[ -d "$PREFIX/test_logs/" ]]; then
        cp -av \
            "$PREFIX/test_logs/" \
            "$WORKSPACE/exported-artifacts/extracted_logs"
    fi

    if [[ -d "$PREFIX/logs/" ]]; then
        cp -av \
            "$PREFIX/logs/" \
            "$WORKSPACE/exported-artifacts/lago_logs"
    fi

    find "$PREFIX" \
        -maxdepth 1 \
        -iname \*.xml \
        -exec mv {{}} "$WORKSPACE/exported-artifacts" \;

    rm -rf "$PREFIX"
fi
