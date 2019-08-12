#!/bin/bash -xe

main() {
    build_dummy_rpm
}

build_dummy_rpm() {
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

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
