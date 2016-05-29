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

## Holds the current step name for logging
(
    set +x
    echo ====================================================================
    echo == "$(basename "$0")"
)

CURRENT_STEP="INIT"
REPOS_FILE="/etc/yum.repos.d/upgrade_test.repo"
ENGINE_PACKAGE="ovirt-engine"

show_error()
{
    if [[ "$CURRENT_STEP" == "FINISHED" ]]; then
        echo "UPGRADE_TESTS::$CURRENT_STEP"
    else
        echo "FAILED::$CURRENT_STEP:: Unrecoverable failure, exitting"
    fi
}


die() {
    local m="${1}"
    echo "FATAL: ${m}"
    exit 1
}


usage() {
    cat << __EOF__
    USAGE:
        > ${0} [parameters]

    PARAMETERS:
        -w|--workspace WORKSPACE
            path to workspace

        -f|--repo-from FROM
            This option can be specified multiple times (at least one).
            This adds the repositories that will be enabled during the first
            installation of the engine before the upgrade

        -t|--repo-to TO
            This option can be specified multiple times (at least one).
            This adds the repositories that will be enabled after the first
            installation. while doing the upgrade

        -c|--cleanup-file CLEANUP_FILE
            Answerfile to use when running cleanup

        -s|--setup-file SETUP_FILE
            Answerfile to use when running setup
        -p|--engine-package ENGINE_PACKAGE_NAME
            specify a custom engine package name
            (optional, default is ovirt-engine)
__EOF__
}


get_opts() {
    local args
    args=$(getopt \
        -o "w:f:t:s:c:p:" \
        -l "workspace:,repo-from:,repo-to:,setup-file:,cleanup-file:,engine-package:" \
        -n "$0" \
        -- "$@")
    [[ $? -ne 0 ]] && exit $?
    eval set -- "$args"
    while true; do
        opt="$1"
        val="$2"
        shift 2 || :
        case "${opt}" in
            -w|--workspace)
                WORKSPACE="${val}"
                ;;
            -f|--repo-from)
                REPOS_FROM="${REPOS_FROM:+$REPOS_FROM,}${val}"
                ;;
            -t|--repo-to)
                REPOS_TO="${REPOS_TO:+$REPOS_TO,}${val}"
                ;;
            -s|--setup-file)
                SETUP_FILE="${val}"
                ;;
            -c|--cleanup-file)
                CLEANUP_FILE="${val}"
                ;;
            -p|--engine-package)
                ENGINE_PACKAGE="${val}"
                ;;
            --) break;;
        esac
    done
    return 0
}


init_postgres() {
    local res=0
    CURRENT_STEP="SETUP::INIT_POSTGRES"
    if rpm -q postgresql-server; then
        service postgresql stop
        yum remove -y postgresql-server
    fi
    ## rm -rf does not complain if the file does not exist
    rm -rf /var/lib/pgsql/data
    yum -y install postgresql-server
    service postgresql initdb || res=$(($res + $?))
    ## ugly fig for the tests to work
    cat >/var/lib/pgsql/data/pg_hba.conf <<EOF
host    all            all        127.0.0.1/0    trust
host    all            all        ::1/128    trust
local   all            all        trust
EOF
    cat /var/lib/pgsql/data/pg_hba.conf
    service postgresql start || res=$(($res + $?))
    sleep 30
    psql -h 127.0.0.1 postgres postgres \
        -c "CREATE USER engine WITH PASSWORD '123456';" \
        || res=$(($res + $?))
    psql -h 127.0.0.1 postgres postgres \
        -c "CREATE DATABASE engine;" \
        || res=$(($res + $?))
    psql -h 127.0.0.1 postgres postgres \
        -c "GRANT ALL PRIVILEGES ON DATABASE engine TO engine;" \
        || res=$(($res + $?))
    [[ "${res}" -ne 0 ]] && die "Failed to init postgres"
    return 0
}


prepare_pgpass() {
    CURRENT_STEP="SETUP::PREPARE_PGPASS"
    cat << PGPASS > $HOME/.pgpass
localhost:5432:*:postgres:123456
localhost:5432:*:engine:123456
127.0.0.1:5432:*:engine:123456
127.0.0.1:5432:*:postgres:123456
PGPASS
    chmod 600 $HOME/.pgpass
}


prepare_database() {
    CURRENT_STEP="SETUP::PREPARE_DB"
    init_postgres
    prepare_pgpass
    return 0
}


prepare_apache()
{
    yum -y install httpd mod_ssl
    sed -i 's/^Listen 80/Listen 127.0.0.1:80/' /etc/httpd/conf/httpd.conf
    sed -i 's/^Listen 443/Listen 127.0.0.1:443/' /etc/httpd/conf.d/ssl.conf
}


pre_clean() {
    local workspace="${1?}"
    local cleanup_file="${2?}"
    CURRENT_STEP="SETUP::PRECLEAN"
    echo "----- Cleaning old rpms... ----"
    sed -i "s/CHANGE_HOSTNAME/${HOSTNAME}/g" "${cleanup_file}"
    # Clean engine rpms
    if rpm -q "$ENGINE_PACKAGE"; then
        engine-cleanup -u 2>/dev/null\
        || engine-cleanup --config-append="${cleanup_file}" \
        || :
    fi
    yum -y remove "$ENGINE_PACKAGE"\* vdsm\* httpd mod_ssl || :
    yum clean all --enablerepo=upgrade_*
    echo "" > /etc/exports
    rm -rf /etc/ovirt-engine
    rm -rf /etc/ovirt-engine-setup.conf.d
    rm -rf /etc/httpd/*
    rm -f "${workspace}"/*log "${workspace}"/*txt
    rm -rf /var/lib/exports/iso
    rm -rf /var/log/ovirt-engine
    return 0
}


## Ugly, but until we have a solution to the ovirt repo installation on the
## slaves, this it will have to do the job
disable_engine_repos() {
    local disabled_repos_list="${1?}"
    local repo
    echo "" > "$disabled_repos_list"
    for repo in /etc/yum.repos.d/*; do
        if grep -qi ovirt "${repo}"; then
            sed -i 's/enabled=1/enabled=0/g' "${repo}"
            echo "$repo" >> "$disabled_repos_list"
        fi
    done
    return 0
}


enable_upgrade_repos() {
    sed -i 's/enabled=0/enabled=1/g' "$REPOS_FILE"
}


append_repo(){
    local repo_file="${1?}"
    local repo_name="${2?}"
    local repo_url="${3?}"
    local repo_enabled="${4:-1}"
        cat << EOF >> "$repo_file"

[$repo_name]
name=$repo_name
baseurl=$repo_url
enabled=$repo_enabled
gpgcheck=0
EOF
    return 0
}


configure_repos() {
    local from_repos="${1?}"
    local to_repos="${2?}"
    local os="$(facter operatingsystem)"
    local i to_repo from_repo
    CURRENT_STEP="SETUP:CONFIGURE_REPOS"
    shopt -s nocasematch
    case $os in
        fedora) os="fc";;
        centos) os="el";;
        RedHat) os="el";;
    esac
    ## disable all the previous ovirt repos, if any
    disable_engine_repos "$workspace/disabled_repos.list"
    ## init the repo file
    cat << EOF > $REPOS_FILE
## Created by ${JOB_URL}
EOF
    ## Add all the repos
    i=0
    for from_repo in ${from_repos//,/ }; do
        append_repo "$REPOS_FILE" "upgrade_from_$i" "$from_repo"
        i="$(($i + 1))"
    done
    i=0
    for to_repo in ${to_repos//,/ }; do
        append_repo "$REPOS_FILE" "upgrade_to_$i" "$to_repo" 0
        i="$(($i + 1))"
    done
    return 0
}


collect_iptables_rules() {
    local dst_file="${1?}"
    iptables-save > "$dst_file"
    return 0
}


install_from_engine() {
    local answer_file="${1?}"
    CURRENT_STEP="SETUP::INSTALLING_ENGINE"
    # Installing 'from' version
    yum -y install "$ENGINE_PACKAGE"
    sed -i "s/CHANGE_HOSTNAME/$HOSTNAME/g" "${answer_file}"
    echo "Installing engine"
    engine-setup --config-append="${answer_file}" \
    || {
        echo "########## SETUP_FAILED"
        return 1
    }
    return 0
}


engine_upgrade() {
    local answer_file="${1?}"
    yum -y update "${ENGINE_PACKAGE}-setup" "${ENGINE_PACKAGE}-dwh-setup"
    echo "Running upgrade setup"
    engine-setup --config-append="${answer_file}"
    return $?
}


wait_for_engine() {
    local ans_file="${1?}"
    local ok=false
    ## give it 5 minutes
    local counter=5
    local password="$(grep -i 'OVESETUP_DB/password' "${ans_file}" \
        | awk -F':' '{print $NF}')"
    local status
    CURRENT_STEP="UPGRADE::WAIT_FOR_ENGINE"
    while ! $ok; do
        status="$(curl --user "admin@internal:${password}" \
            -I \
            --insecure https://localhost/ovirt-engine/api \
            | head -n 1 | awk '{print $2}')"
        if [[ "${status}" -ne 200 ]]; then
            counter=$((counter - 1))
            if [[ $counter -eq 0 ]]; then
                return 1
            fi
            sleep 60
        else
            ok=true
        fi
    done
    return 0
}


setup_env()
{
    local workspace="${1?}"
    local setup_file="${2?}"
    local cleanup_file="${3?}"
    local repos_from=${4?}
    local repos_to=${5?}
    CURRENT_STEP="SETUP"
    ## prepare the logs dir
    [[ -d "$workspace/logs" ]] || mkdir -p "$workspace/logs"
    ## Configure all the repos (before the clean so the metadata gets cleaned up)
    configure_repos "$repos_from" "$repos_to"
    ## Make sure no dirty env
    pre_clean "$workspace" "$cleanup_file"
    ## Prepare the database and permissions
    prepare_database
    ## Make sure apache only listens on localhost, as it collides with
    ## minidell ssh tunnels...
    prepare_apache
    install_from_engine "$setup_file"
    collect_iptables_rules "$workspace/logs/iptables_before_upgrade.txt"
    echo "Some yum information"
    yum versionlock list
    yum list installed "${ENGINE_PACKAGE}"\*
    yum grouplist
    return 0
}


run_upgrade()
{
    local workspace="${1?}"
    local answer_file="${2?}"
    CURRENT_STEP="UPGRADE"
    enable_upgrade_repos
    engine_upgrade "$answer_file"
    collect_iptables_rules "$workspace/logs/iptables_after_upgrade.txt"
    echo "Some yum information"
    yum versionlock list
    yum list installed "${ENGINE_PACKAGE}"\*
    yum grouplist
    wait_for_engine "$answer_file"
    return 0
}


### MAIN
unset WORKSPACE SETUP_FILE CLEANUP_FILE REPOS_FROM REPOS_TO
get_opts "${@}"
[[ -n "${WORKSPACE}" ]] || die "Please specify the workspace"
[[ -n "${REPOS_TO}" ]] \
    || die "Please specify at least one repository to update to"
[[ -n "${REPOS_FROM}" ]] \
    || die " Please specify at least one repository to upgrade from"
[[ -n "${CLEANUP_FILE}" ]] || die " Please specify a cleanup answer file"
[[ -n "${SETUP_FILE}" ]] || die " Please specify a setup answer file"

trap "show_error" EXIT
cat <<EOM
Starting upgrade tests:
    from repos: ${REPOS_FROM}
    to repos: ${REPOS_TO}
EOM

setup_env "$WORKSPACE" \
    "$SETUP_FILE" "$CLEANUP_FILE" \
    "$REPOS_FROM" "$REPOS_TO"
run_upgrade "$WORKSPACE" "$SETUP_FILE"
CURRENT_STEP="FINISHED"
