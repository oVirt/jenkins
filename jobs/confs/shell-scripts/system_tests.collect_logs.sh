#!/bin/bash -xe
echo 'shell_scripts/system_tests.collect_logs.sh'

WORKSPACE=$PWD

PREFIX="$WORKSPACE/lago-prefix"

if [[ -d "$PREFIX" ]]; then
    rm -rf \
        "$WORKSPACE/exported-artifacts"

    mkdir -p "$WORKSPACE/exported-artifacts"

    if [[ -d "$PREFIX/test_logs/" ]]; then
        cp -av \
            "$PREFIX/test_logs/" \
            "$WORKSPACE/exported-artifacts/extracted_logs"
    fi

    if [[ -d "$PREFIX/logs/" ]]; then
        cp -av \
            "$PREFIX/logs/" \
            "$WORKSPACE/exported-artifacts/testenv_logs"
    fi

    find "$PREFIX" \
        -maxdepth 1 \
        -iname \*.xml \
        -exec mv {{}} "$WORKSPACE/exported-artifacts" \;

    rm -rf "$PREFIX"
fi
