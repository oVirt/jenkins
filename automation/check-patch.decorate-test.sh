#!/bin/bash -ex
# A testing script to run inside a container that is a part of a decorated POD
# that has source cloning and artifact collection services
#
main() {
    test_pwd
    test_exported_artifacts
    test_secrets
}

test_pwd() {
    echo "Hello from '$0'"!
    echo "PWD is $PWD"
    [[ $PWD == /workspace ]]
}

test_exported_artifacts() {
    ls -la /exported-artifacts
    [[ -d /exported-artifacts ]]
    echo "This is an artifact!" > /exported-artifacts/artifact1.txt
    echo "This is another artifact!" > /exported-artifacts/artifact2.txt
    ls -la /exported-artifacts
}

test_secrets() {
    [[ -e automation/secret-data.txt ]]
    echo 'The big secret' | cmp - automation/secret-data.txt
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
