#!/bin/bash -e
# mk_refspec_include.sh - Make a JJB include file that contains the
#                         current Git SHA
#
# This script must be run from the `jobs/confs` directory
#
mk_refspec_include() {
    local refspec_file='includes/stdci-scm-refspec.inc'
    if type -p git >> /dev/null && [[ -e "$refspec_file" ]]; then
        git rev-parse HEAD > "$refspec_file"
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    mk_refspec_include "$@"
fi
