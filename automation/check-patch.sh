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
    changed_files="$(python3 $usrc changed-files)"

    if grep -q '^mock_configs/' <<< "$changed_files"; then
        test_standard_ci "$@"
    fi
    if grep -q '\.py$' <<< "$changed_files"; then
        test_python_scripts "$@"
    fi
    local package_files='data/dummy.spec|collect_artifacts.sh|automation/.*\.dummy-rpm\..*'
    if grep -qE "($package_files)" <<< "$changed_files"; then
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

test_standard_ci() {
    test_standard_ci_proxy
}


install_python_test_deps() {
    local python_cmd="${1:?}"

    "$python_cmd" -m pip install -U pip
    "$python_cmd" -m pip install -r 'test-requirements.lock'
}

test_python_scripts() {
    local versions=(2 3)
    local version _python
    local tested=false

    for version in "${versions[@]}"; do
        _python="python${version}"
        command -v "$_python" || {
            echo "$_python command was not found, skipping tests" 1>&2
            continue
        }
        install_python_test_deps "$_python"
        echo "Successfully installed test dependencies with $_python" 1>&2
        run_pytest "$_python"
        tested=true
    done

    "$tested" && return
    (
        echo "Python versions ${versions[*]} weren't found"
        echo "Failed to execute Python tests"
    ) 1>&2

    return 1
}

run_pytest() {
    local python_cmd="${1:?}"

    "$_python" \
        -m pytest \
        -vv \
        --junitxml="exported-artifacts/${python_cmd}-pytest.junit.xml" \
        test
}

test_rpmbuild() {
    # Build an RPM to test RPM-related processes
    source automation/build-artifacts.dummy-rpm.sh

    build_dummy_rpm
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
    readonly HW_ENV_VARS=(
        GIT_COMMITTER_{NAME,EMAIL}
        BUILD_{NUMBER,ID,DISPLAY_NAME,TAG,URL} JOB_{{,BASE_}NAME,URL}
        NODE_{NAME,LABELS} WORKSPACE JENKINS_URL GERRIT_BRANCH
    )
    for var_name in "${HW_ENV_VARS[@]}"; do
        local var_value="${!var_name}"
        echo "$var_name: $var_value"
        [[ $var_value ]] || return 1
    done
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

     test_ci_toolbox_in_path || exit "$?"
}

test_ci_toolbox_in_path() {
    type -P dummy.sh && { echo "${FUNCNAME[0]} SUCCESS"; return 0; }
    echo "${FUNCNAME[0]} FAILED - ci toolbox is not in the PATH"
    return 1
}

main "$@"
