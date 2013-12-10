#!/bin/bash

res=0
## List of matches for dirs that might have rspec tests
## The grouped pattern must be the directory where the spec directory is
## located
DIRS=(
    "^(site/ovirt-infra).*"
    "^(modules/[^/]+).*"
    "^(profiles/[^/]+).*"
)


function has_spec()
{
    dir="${1?}"
    for match_dir in "${DIRS[@]}"; do
        if [[ $dir =~ $match_dir ]] \
        && [[ -d "${BASH_REMATCH[1]}/spec" ]]; then
            echo "${BASH_REMATCH[1]}"
            return 0
        fi
    done
    return 1
}


function is_in()
{
    what="${1?}"
    shift
    for arg in "$@"; do
        if [[ "$arg" == "$what" ]]; then
            return 0
        fi
    done
    return 1
}


echo "@@@ Starting rspec tests for the modified modules (if any) @@@"
## Get the list of modules that changed
#for dir in $(git diff --name-only HEAD^1 \
#             | sort | uniq); do
changed_dirs=()
for changed_file in "lerele/tocoto.pp" "modules/mymod" \
    "profiles/myprof/popo.pp" "site/ovirt-infra/lolo.pp"; do
    if spec_dir="$(has_spec "${changed_file}")" \
    && ! is_in "$spec_dir" "${changed_dirs[@]}"; then
        changed_dirs+=("$changed_dir")
    fi
done

## Run the tests on the changed modules
for changed_dir in "${changed_dirs[@]}"; do
    if spec_dir="$(has_spec "$changed_file")"; then
        echo "###### Starting tests for module $dir"
        pushd "$dir"
        rspec
        res=$((res + $?))
        popd
        echo "######################################"
    fi
done

if [[ $res -gt 0 ]]; then
    echo "@@@ RSPEC FAILED @@@"
    exit 1
else
    echo "@@@ RSPEC PASSED, CONGRATULATIONS @@@"
fi
