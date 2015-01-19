#!/bin/bash
echo 'shell_scripts/system_tests.collect_logs.sh'
PREFIX="${{WORKSPACE:?}}/jenkins-deployment-${{BUILD_NUMBER:?}}"

cd "${{WORKSPACE}}"
if [[ -d "${{PREFIX}}" ]]; then
    rm -rf \
        "${{WORKSPACE}}/exported-archives" \
        "${{WORKSPACE}}/exported-archives.tar.gz"

    mkdir "${{WORKSPACE}}/exported-archives"

    if [[ -d "${{PREFIX}}/test_logs/" ]]; then
        cp -av \
            "${{PREFIX}}/test_logs/" \
            "${{WORKSPACE}}/exported-archives/extracted_logs"
    fi

    if [[ -d "${{PREFIX}}/logs/" ]]; then
        cp -av \
            "${{PREFIX}}/logs/" \
            "${{WORKSPACE}}/exported-archives/testenv_logs"
    fi

    if [[ -d "${{PREFIX}}/build" ]]; then
        find "${{PREFIX}}/build" \
            -name "*.rpm" \
            -exec rm -f "{{}}" \;

        cp -av \
            "${{PREFIX}}/build" \
            "${{WORKSPACE}}/exported-archives/build_logs"
    fi

    rm -rf "${{PREFIX}}"
    tar cvzf \
        "exported-archives.tar.gz" \
        "exported-archives/"
fi
