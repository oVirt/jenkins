#!/bin/bash -e
# dummy_suit_master.sh - A dummy system tests suit that does nothing ATM
#
main() {
    echo "This is a dummy system tests suit that does nothing"
    echo
    show_extra_sources
    check_gated_gepo
    echo "All done."
}

show_extra_sources() {
    echo "Dump of provided extra_sources follows:"
    echo "---------------------------------------"
    cat extra_sources
    echo "---------------------------------------"
    echo
}

check_gated_gepo() {
    echo "Dump of suit repos file follows:"
    echo "--------------------------------"
    cat automation/dummy_suite_master.yumrepos
    echo "--------------------------------"
    echo
    if
        yum -c automation/dummy_suite_master.yumrepos repolist -q \
        | grep gated-dummy-master-el7
    then
        echo "---> Found gated repo in configuration"
        return 0
    else
        echo "---> Gated repo missing from configuration"
        return 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
