#!/bin/bash -xe
set +o noglob

main() {
    # dispatch tests according to what changed in git
    local changed_files
    changed_files="$(git show --pretty="format:" --name-only)"

    if echo "$changed_files" | grep -q '^mock_configs/'; then
        test_standard_ci "$@"
    fi
    if echo "$changed_files" | grep -q '^jobs/'; then
        # we only run jjb on el7/x86)64 so skip otherwise
        if is_jjb_test_arch; then
            test_job_configs "$@"
        else
            echo "Skipped JJB testing on this platform"
        fi
    fi
}

is_jjb_test_arch() {
    [[ "$(uname -m)" == "x86_64" ]] &&
        grep -qE '^(Red Hat|CentOS) .* release 7\.' /etc/system-release
}

test_job_configs() {
    sh -xe automation/jenkins_check_yaml.sh
    python automation/check_publishers_not_deleted.py
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
    test_standard_ci_proxy
    test_mock_genconfig
}

main "$@"
