#!/bin/bash
echo 'shell_scripts/system_tests.cleanup.sh'
PREFIX="${{WORKSPACE:?}}/jenkins-deployment-${{BUILD_NUMBER:?}}"
cd "${{PREFIX}}"
testenvcli cleanup
