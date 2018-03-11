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
    local containers_flow="Dockerfiles|collect_artifacts.sh|standard-stage.yaml|cleanup_slave.sh"
    if grep -qE "(${containers_flow})" <<< "$changed_files"; then
        # docker is not supported in official el6
        if is_docker_test_arch; then
            test_docker_container
        fi
    fi
    if grep -q '^mock_configs/' <<< "$changed_files"; then
        test_standard_ci "$@"
    fi
    if grep -q '^jobs/' <<< "$changed_files"; then
        # we only run jjb on el7/x86)64 so skip otherwise
        if is_jjb_test_arch; then
            test_job_configs "$@"
        else
            echo "Skipped JJB testing on this platform"
        fi
    fi
    if grep -q '\.py$' <<< "$changed_files"; then
        test_python_scripts "$@"
    fi
    if grep -q 'data/dummy.spec' <<< "$changed_files"; then
        test_rpmbuild "$@"
    fi
    test_secrets_and_credentials
}

is_jjb_test_arch() {
    [[ "$(uname -m)" == "x86_64" ]] &&
        grep -qE '^(Red Hat|CentOS) .* release 7\.' /etc/system-release
}

is_docker_test_arch() {
    [[ "$(uname -m)" != "s390x" ]] &&
        ! grep -qE '^(Red Hat|CentOS) release 6\.' /etc/system-release
}

test_job_configs() {
    sh -xe automation/jenkins_check_yaml.sh
}

test_standard_ci_repos() {
    if find /etc/yum.repos.d/ -type f | grep -qF ''; then
        echo "Unwanted repo files found in chroot image"
        return 1
    fi
}

test_standard_ci_proxy() {
    if [[ -n "$http_proxy" ]]; then
        echo "It looked like we are running in a PROXIED environment"
        echo "http_proxy='$http_proxy'"
    fi
}

test_mock_genconfig() {
    # skip this test on el6 because we're no longer using it on the
    # Jenkins slaves
    grep -qE '^(Red Hat|CentOS) .*release 6\.' /etc/system-release && \
        return
    for mock_cfg in mock_configs/*.cfg; do
        mock_configs/mock_genconfig --base "$mock_cfg" --name 'foo'
    done
}

test_standard_ci() {
    test_standard_ci_repos
    test_standard_ci_proxy
    test_mock_genconfig
}

test_python_scripts() {
    mkdir -p exported-artifacts
    pip install -r 'test-requirements.txt'
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
    if git describe >& /dev/null; then
        release="$(
            git describe --dirty=.dr |
            sed -re 's/-([0-9])/p\1/;s/-g/git/'
        )"
    else
        release="0.0.0.git$(git describe --always --dirty=.dr)"
    fi
    chown $USER:$USER data/dummy.spec
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

test_secrets_and_credentials() {
    # Check if secrets were injected and parsed correctly from secrets file
    # In our secrets file we hold a dummy secret named jenkins-check-patch
    # with username and password dummy keys (JenkinsUsername & JenkinsPassword)
    [[ "${test_secret_username}" = "JenkinsUsername" ]] || return 1
    [[ "${test_secret_password}" = "JenkinsPassword" ]] || return 1
    [[ "${test_secret_specified}" = "OVIRT_CI" ]] || return 1
    return 0
}

main "$@"
