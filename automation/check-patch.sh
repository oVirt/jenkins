#!/bin/bash -xe
set +o noglob

main() {
    # This can cause issues if standard-CI impelmentation is not safe
    # (see https://ovirt-jira.atlassian.net/browse/OVIRT-992)
    rm -rf exported-artifacts
    mkdir exported-artifacts

    local usrc="scripts/usrc.py"
    [[ -x "$usrc" ]] || usrc="scripts/usrc_local.py"

    # dispatch tests according to what changed in git
    local changed_files
    changed_files="$($usrc changed-files)"

    # These are the files which are involved with the containers flow
    local containers_flow="Dockerfiles|collect_artifacts.sh|standard-stage.yaml|cleanup_slave.sh|docker_cleanup.py"
    if grep -qE "(${containers_flow})" <<< "$changed_files"; then
        if is_docker_test_arch; then
            test_docker_container
        fi
    fi
    if grep -q '^mock_configs/' <<< "$changed_files"; then
        test_standard_ci "$@"
    fi
    if grep -q '\.py$' <<< "$changed_files"; then
        test_python_scripts "$@"
    fi
    if grep -qE '(data/dummy.spec|collect_artifacts.sh)' <<< "$changed_files"; then
        test_rpmbuild "$@"
    fi
    test_secrets_and_credentials
    test_mock_runner_mounts
    test_mock_runner_fd_leak
    test_mock_runner_hardwired_env
    test_ci_toolbox
}

is_docker_test_arch() {
    [[ "$(uname -m)" != "s390x" ]]
}

test_job_configs() {
    sh -xe automation/jenkins_check_yaml.sh
}

test_standard_ci_proxy() {
    #shellcheck disable=2154
    if [[ -n "$http_proxy" ]]; then
        echo "It looked like we are running in a PROXIED environment"
        echo "http_proxy='$http_proxy'"

        if [[ "$no_proxy" == *localhost* ]]; then
            echo "It seems that no_proxy is properly set to '$no_proxy'"
        else
            echo "It seems that no_proxy is not set, local connections"
            echo "will probably fail"
            return 1
        fi
    fi
}

test_mock_genconfig() {
    for mock_cfg in mock_configs/*.cfg; do
        mock_configs/mock_genconfig --base "$mock_cfg" --name 'foo'
    done
}

test_standard_ci() {
    test_standard_ci_proxy
    test_mock_genconfig
}

test_python_scripts() {
    mkdir -p exported-artifacts
    pip install -U pip
    pip install -r 'test-requirements.lock'
    python -m pytest -vv --junitxml='exported-artifacts/pytest.junit.xml' test
    if command -v py.test-3; then
        # If we have python3 (e.g we're on fedora) run tests in python 3 too
        python3 -m pytest -vv \
            --junitxml='exported-artifacts/pytest3.junit.xml' test
    fi
}

test_rpmbuild() {
    # Build an RPM to test RPM-related processes
    local version release

    version='0.1.0'
    release="0.$(git log --oneline | wc -l)"
    chown "$USER:$USER" data/dummy.spec
    rpmbuild \
        --define '_rpmdir exported-artifacts' \
        --define '_srcrpmdir exported-artifacts' \
        --define "_version $version" \
        --define "_release $release" \
        -ba data/dummy.spec
}

test_docker_container() {
    # Build a dummy container and run it
    # we also tag it with exported-artifacts to test the export
    local export_tag="exported-artifacts"
    docker build -t check_patch_container:$export_tag data/Dockerfiles/
    docker run check_patch_container:$export_tag
}

#shellcheck disable=2154
test_secrets_and_credentials() {
    # Check if secrets were injected and parsed correctly from secrets file
    # In our secrets file we hold a dummy secret named jenkins-check-patch
    # with username and password dummy keys (JenkinsUsername & JenkinsPassword)
    [[ "${test_secret_username}" = "JenkinsUsername" ]] || return 1
    [[ "${test_secret_password}" = "JenkinsPassword" ]] || return 1
    [[ "${test_secret_specified}" = "OVIRT_CI" ]] || return 1
    return 0
}

test_mock_runner_mounts() {
    # Verify that mock runner can mount directories and create them if they are
    # missing
    (
        set +x
        cut -d: -f2 automation/check-patch.mounts | grep -v sock \
        | while read d; do
            echo -n "Testing mounted dir: $d: "
            if ! [[ -d $d ]]; then
                echo 'FAILED - not a directory'
                exit 1
            fi
            if ! grep -q " $d " /proc/mounts; then
                echo 'FAILED - not mounted'
                exit 1
            fi
            echo SUCCESS
        done
    )
}

test_mock_runner_fd_leak() {
    # Verify that mock_runner doesn't leack it's stdin to user's script
    # If we reached timeout, it means that stdin is empty
    # If $A is empty it means that stdin is empty
    local res A
    # shellcheck disable=2034
    read -t 2 A && timeout 2s cat > /dev/null
    res=$?
    if (( res == 0 || res == 142 )); then
        echo "ERROR: There is a file descriptor leakage!"
        return 1
    else
        return 0
    fi
}

test_mock_runner_hardwired_env() {
    echo "GIT_COMMITTER_NAME: $GIT_COMMITTER_NAME"
    echo "GIT_COMMITTER_EMAIL: $GIT_COMMITTER_EMAIL"
    if [[ $GIT_COMMITTER_NAME ]] && [[ $GIT_COMMITTER_EMAIL ]]; then
        return 0
    else
        return 1
    fi
}

test_ci_toolbox() {
    # Ensure that ci_toolbox is mounted and the tools there are usable
    local toolbox=/var/lib/ci_toolbox
    local out

    (
        set +x
        for tool in dummy.sh linked_dummy.sh; do
            echo -n "Checking toolbox script: $tool:"
            if ! [[ -x "$toolbox/$tool" ]]; then
                echo " FAILED - not executable"
                exit 1
            fi
            out="$("$toolbox/$tool")"
            if ! [[ $out == "$toolbox/$tool" ]]; then
                echo " FAILED - wrong returned location: $out"
                exit 1
            fi
            echo " SUCCESS"
        done
    )
}

main "$@"
