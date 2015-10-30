#!/bin/bash -xe
echo 'shell_scripts/system_tests.cleanup.sh'

WORKSPACE=$PWD

PREFIX="$WORKSPACE/lago-prefix"

cd "$PREFIX"
lagocli cleanup
