#!/bin/bash -x
# ./update_engine_params.sh <workspace> <from version> <to version>

WORKSPACE=$1
FROM=$2
TO=$3
ANS_FILE="${WORKSPACE}"/jenkins/jobs/ovirt_engine_upgrade_params/answer.file.otopi
CLEANUP_FILE="${WORKSPACE}"/jenkins/jobs/ovirt_engine_upgrade_params/cleanup.file.otopi
DATE=$(date +"%a_%b_%d_%H_%M_%S_%Z_%Y")
LOG="${WORKSPACE}/${DATE}.log"
HOSTNAME=$(hostname)
OS="$(awk '{print $1}' /etc/redhat-release | tr -s '[A-Z]' '[a-z]')"


validate()
{
    if [[ -z "${WORKSPACE}" \
        || -z "${TO}"  \
        || -z "${FROM}" ]]; then
        echo "Please provide 3 parameters to the job"
        exit 1
    fi
}


init_postgres()
{
    local res=0
    if rpm -q postgresql-server; then
        service postgresql stop
        yum remove -y postgresql-server
    fi
    ## rm -rf does not complain if the file does not exist
    rm -rf /var/lib/pgsql/data
    yum -y install postgresql-server
    postgresql-setup initdb || res=$(($res + $?))
    ## ugly fig for the tests to work
    cat >/var/lib/pgsql/data/pg_hba.conf <<EOF
host    all            all        127.0.0.1/0    trust
host    all            all        ::1/128    trust
local   all            all        trust
EOF
    cat /var/lib/pgsql/data/pg_hba.conf
    service postgresql start || res=$(($res + $?))
    # Wait a few seconds to give time for the database to start up on
    # slow systems
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
    if [[ "${res}" -ne 0 ]]; then
        echo "Failed to init postgres"
        exit 1
    fi
}


pre_clean()
{
    echo "----- Cleaning old rpms... ----"
    sed -i "s/CHANGE_HOSTNAME/$HOSTNAME/g" "${CLEANUP_FILE}"
    # Clean engine rpms
    if rpm -q ovirt-engine; then
        engine-cleanup -u \
            || engine-cleanup --config-append="${CLEANUP_FILE}"
    fi
    yum -y remove ovirt-engine\* vdsm\* httpd mod_ssl
    rm -rf /etc/httpd/*
    rm -f "${WORKSPACE}"/*log "${WORKSPACE}"/*txt
    echo "" > /etc/exports
    rm -rf /var/lib/exports/iso
}


disable_engine_repos()
{
    for repo in /etc/yum.repos.d/*; do
        grep -qi ovirt "$repo" \
            && sed -i 's/enabled=1/enabled=0/g' "$repo"
    done
}


enable_engine_repos()
{
    for repo in /etc/yum.repos.d/*; do
        grep -qi ovirt "$repo" \
            sed -i 's/enabled=0/enabled=1/g' "$repo"
    done
}


configure_repo()
{
    local _release=$1
    local _os=""

    if [[ "${OS}" == "fedora" ]]; then
        _os="Fedora"
    elif [[ "${OS}" == "centos" ]]; then
        _os="EL"
    else
        echo "${_os} is not supported"
        exit 1
    fi

    cat << EOF > /etc/yum.repos.d/upgrade_params_${_release}.repo
[ovirt-engine-${_release}]
name=oVirt Engine ${_release}
baseurl=http://ovirt.org/releases/${_release}/rpm/${_os}/\$releasever/
enabled=1
gpgcheck=0
EOF
}


copy_log()
{
    LOG_NAME=$(ls -trll /var/log/ovirt-engine/setup | tail -n1 | grep -o "[^ ]*[.]log$")
    cp -f /var/log/ovirt-engine/setup/"${LOG_NAME}" "${WORKSPACE}"
}


collect_iptables_rules()
{
    _filename=$1
    iptables-save > "${WORKSPACE}"/"${_filename}".txt
}


install_from_engine()
{
    # Installing from version
    yum -y install ovirt-engine --enablerepo=ovirt-engine-${FROM}

    ENGINE_UPGRADE="engine-setup --config-append="${ANS_FILE}""
    ENGINE_CLEANUP="engine-cleanup --config-append="${CLEANUP_FILE}""
    ENGINE_SETUP=${ENGINE_UPGRADE}
    sed -i "s/CHANGE_HOSTNAME/$HOSTNAME/g" "${ANS_FILE}"

    echo "Installing ${FROM} engine"
    ${ENGINE_SETUP}
    if [[ "${?}" -ne 0 ]]; then
        echo "SETUP_FAILED" >> "${LOG}"
        copy_log
        exit 1
    fi
    copy_log
    collect_iptables_rules "before_upgrade"
}


prepare_pgpass()
{
    cat << PGPASS > /root/.pgpass
localhost:5432:*:postgres:123456
localhost:5432:*:engine:123456
127.0.0.1:5432:*:engine:123456
127.0.0.1:5432:*:postgres:123456
PGPASS

    chmod 600 /root/.pgpass
}


remove_pgpass()
{
    rm -f /root/.pgpass
}


engine_upgrade()
{
    yum -y update ovirt-engine-setup
    echo "Upgrading from $FROM to $TO"
    ${ENGINE_UPGRADE}
    if [[ "${?}" -ne 0 ]]; then
        echo "UPGRADE_FAILED" >> ${LOG}
    fi
    copy_log
    collect_iptables_rules "after_upgrade"
    echo "" >> ${LOG}
}


check_engine_status()
{
    sleep 60
    local _password=$(grep -i 'OVESETUP_DB/password' ${ANS_FILE} \
                      | awk -F':' '{print $NF}')
    local _status=$(curl --user "admin@internal:${_password}" \
                    -I \
                    --insecure https://localhost/api \
                    | head -n 1 | awk '{print $2}')

    if [[ "${_status}" -ne 200 ]]; then
        echo "ENGINE_STATUS_ERROR" >> "${LOG}"
    fi
}


post_clean()
{
    # Cleanup stage
    rm -f /etc/yum.repos.d/upgrade_params_"${FROM}".repo \
        /etc/yum.repos.d/upgrade_params_"${TO}".repo
    ${ENGINE_CLEANUP} || echo "CLEANUP_FAILED" >> "${LOG}"
    copy_log
}


main()
{
    validate
    pre_clean
    init_postgres
    disable_engine_repos
    prepare_pgpass
    configure_repo "${FROM}"
    install_from_engine
    configure_repo "${TO}"
    engine_upgrade
    check_engine_status
    post_clean
    enable_engine_repos
    remove_pgpass
}

main
