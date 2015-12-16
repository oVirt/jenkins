#!/bin/bash -ex

## Copyright (C) 2014 Red Hat, Inc., Kiril Nesenko <knesenko@redhat.com>
### This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.

## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

ENGINE_PACKAGE="ovirt-engine"

usage() {
    local rc="$1"
    local msg="$2"
    msg="$msg
    USAGE:
        > ${0} [parameters]

    PARAMETERS:
        -w|--workspace WORKSPACE
            path to workspace

        -c|--cleanup-file CLEANUP_FILE
            Answerfile to use when running cleanup
        -p|--engine-package ENGINE_PACKAGE_NAME
            specify a custom engine package name
            (optional, default is ovirt-engine)"
    [[ -n "$rc" ]] && die "$msg" "$rc"
}


die() {
    local msg="$1"
    local rc="${2:-1}"
    echo "${msg}"
    exit $rc
}

store(){
    local what="${1?}"
    local where="${2?}"
    tar cvzf "$where/${what//\//_}.tgz" "$what"
}

archive_logs_in_dirs(){
    local dst_dir="${1?}"
    local dir
    for dir in "${@:2}"; do
        if [[ ! -d "$dir" ]]; then
            continue
        fi
        find "$dir" -iname "*.log" | while read file; do
            store "$file" "$dst_dir"
        done
    done
}

archive_engine_logs(){
    local workspace="${1?}"
    local dst_dir="${2?}"
    archive_logs_in_dirs "$dst_dir" /var/log/ovirt-engine "$workspace/tmp_repo"
    return $?
}

## This is the last function executed always when the script ends
cleanup()
{
    local workspace="${1?}"
    local cleanup_file="${2?}"
    local rc=0
    rm -f /etc/yum.repos.d/upgrade_test.repo
    if which engine-setup &>/dev/null; then
        engine-cleanup --config-append="${cleanup_file}" \
        || :
    fi
    yum -y remove "$ENGINE_PACKAGE"\* vdsm\* httpd mod_ssl || :
    rm -f /root/.pgpass
    enable_engine_repos "$workspace/disabled_repos.list"
}


get_opts() {
    local opt val opts
    opts=$(getopt \
        -o 'w:c:p:h' \
        -l 'workspace:,cleanup-file:,engine-package:,help' \
        -n "$0" \
        -- "$@")
    [[ $? -eq 0 ]] || help 1;
    eval set -- "$opts"
    while true; do
        opt="$1"
        val="$2"
        shift && shift || :
        case "${opt}" in
            -w|--workspace)
                WORKSPACE="${val}";;
            -c|--cleanup-file)
                CLEANUP_FILE="${val}";;
            -p|--engine-package) ENGINE_PACKAGE="${val}";;
            -h|--help) usage 0;;
            --) break;;
        esac
    done
}


enable_engine_repos() {
    local disabled_repos_list="${1?}"
    local repo
    [[ -f "$disabled_repos_list" ]] || return 0
    while read -r repo; do
        [[ -f "$repo" ]] || continue
        sed -i 's/enabled=0/enabled=1/g' "${repo}"
    done < "$disabled_repos_list"
}


### MAIN
unset WORKSPACE CLEANUP_FILE
get_opts "${@}"
[ -n "${WORKSPACE}" ] || die "Please specify the workspace"
[ -n "${CLEANUP_FILE}" ] || die " Please specify a cleanup answer file"
cleanup "$WORKSPACE" "$CLEANUP_FILE"
archive_engine_logs "$WORKSPACE" "$WORKSPACE"/logs
