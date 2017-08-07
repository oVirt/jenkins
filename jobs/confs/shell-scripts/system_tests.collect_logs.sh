#!/bin/bash -xe
echo 'shell_scripts/system_tests.collect_logs.sh'

#
# Required jjb vars:
#    version
#
VERSION={version}
SUITE_TYPE={suite_type}
PROJECT={project}

WORKSPACE="${{WORKSPACE:-$PWD}}"
TESTS_LOGS="$WORKSPACE/$PROJECT/exported-artifacts"

rm -rf "$WORKSPACE/exported-artifacts"
mkdir -p "$WORKSPACE/exported-artifacts"

if [[ -d "$TESTS_LOGS" ]]; then
    mv "$TESTS_LOGS/"* "$WORKSPACE/exported-artifacts/"
fi

# export reposync-config.repo and extra_sources so we know the
# repose we used
suit_dir="$PROJECT/${{SUITE_TYPE}}-suite-${{VERSION}}"
cp "$suit_dir"/*.repo exported-artifacts
if [[ -f '$PROJECT/extra_sources' ]]; then
    cp $PROJECT/extra_sources exported-artifacts
fi
