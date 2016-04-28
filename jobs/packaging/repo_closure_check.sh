#!/bin/sh

## Copyright (C) 2014 Red Hat, Inc., Kiril Nesenko <knesenko@redhat.com>
## Copyright (C) 2015 Red Hat, Inc., Sandro Bonazzola <sbonazzo@redhat.com>
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

LAYOUT=""
CUSTOM_URL=""
BASE_URL="http://resources.ovirt.org"
CENTOS_MIRROR="http://centos.mirror.constant.com/"
EPEL_MIRROR="http://mirror.switch.ch/ftp/mirror"
FEDORA_MIRROR="http://mirrors.kernel.org/"
JPACKAGE_MIRROR="http://ftp.heanet.ie/pub"
COPR="http://copr-be.cloud.fedoraproject.org/results"
STATIC_RP=""

die() {
    local msg="${1}"
    echo "FATAL: ${msg}"
    exit 1
}

usage() {
    cat << __EOF__
    ${0} [options]
    --distribution             - Distribution you want to test
    --layout                   - Layout you want to use [old, new]
    --repo                     - Repository you want to test
    --distribution-version     - Distribution version (6,19)
    --static-repo              - Use static repo for nightly (needed for a new layout only)

    Example:
        new layout:
    ${0} --distribution=fc --layout=new --distrinbution-version=20 --repo=ovirt-3.3-snapshot --static-repo=ovirt-3.3-snapshot-static
    ${0} --distribution=el --layout=new --distribution-version=6 --repo=ovirt-3.3-snapshot --static-repo=ovirt-3.3-snapshot-static

    old layout:
    ${0} --distribution=Fedora --layout=old --distribution-version=20 --repo=test-repo
    ${0} --distribution=EL --layout=old --distribution-version=6 --repo=test-repo
__EOF__
}

get_opts() {
    while [[ -n "${1}" ]]; do
        opt="${1}"
        val="${opt#*=}"
        shift
        case "${opt}" in
            --repo=*)
                REPO_NAME="${val}"
                ;;
            --distribution=*)
                DISTRIBUTION="${val}"
                ;;
            --distribution-version=*)
                DISTRIBUTION_VERSION="${val}"
                ;;
            --layout=*)
                LAYOUT="${val}"
                ;;
            --static-repo=*)
                STATIC_REPO="${val}"
                ;;
            *)
                usage
                die "Wrong option"
                ;;
        esac
    done
}

validation() {
    [[ -n "${DISTRIBUTION}" ]] || die "Please specify --distribution= option"
    [[ -n "${REPO_NAME}" ]] || die "Please specify --repo= option"
    [[ -n "${DISTRIBUTION_VERSION}" ]] || die "Please specify --distribution-version= option"
    [[ -n "${LAYOUT}" ]] || die "Please specify --layout= option"
}

check_layout() {
    local dist distver static_url repo
    if [[ "${LAYOUT}" == "new" ]]; then
        repo="${DISTRIBUTION}${DISTRIBUTION_VERSION}"
        BASE_URL="${BASE_URL}/pub"
    elif [[ "${LAYOUT}" == "old" ]]; then
        if [ "${DISTRIBUTION}" = "el" ]; then
            dist="EL"
        elif [ "${DISTRIBUTION}" = "fc" ]; then
            dist="Fedora"
        fi
        repo="${dist}/${DISTRIBUTION_VERSION}"
        BASE_URL="${BASE_URL}/releases"
    else
        die "Please provide layout paramter"
    fi
    CUSTOM_URL="${BASE_URL}/${REPO_NAME}/rpm/${repo}"

    if [[ -n "${STATIC_REPO}" ]]; then
        static_url="${BASE_URL}/${STATIC_REPO}/rpm/${repo}"
        distver="$DISTRIBUTION$DISTRIBUTION_VERSION"
        STATIC_RP="--repofrompath=check-custom-static-$distver,${static_url} -l check-custom-static-$distver"
    fi
}

check_repo_closure() {
    local distid="$DISTRIBUTION$DISTRIBUTION_VERSION"
    if [[ "${DISTRIBUTION}" == "el" ]] \
        || [[ "${DISTRIBUTION}" == "Centos" ]]; then
        if [[ "${DISTRIBUTION_VERSION}" == "7" ]]; then
            repoclosure \
                --tempcache \
                --repofrompath=check-custom-"${distid}","${CUSTOM_URL}" ${STATIC_RP} \
                --repofrompath=check-base-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/os/x86_64/ \
                --repofrompath=check-updates-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/updates/x86_64/ \
                --repofrompath=check-extras-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/extras/x86_64/ \
                --repofrompath=centos-ovirt36-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/virt/x86_64/ovirt-3.6/ \
                --repofrompath=check-epel-"${distid}","${EPEL_MIRROR}"/epel/"${DISTRIBUTION_VERSION}"/x86_64/ \
                --repofrompath=centos-glusterfs37-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/storage/x86_64/gluster-3.7/ \
                --repofrompath=check-patternfly-"${distid}","${COPR}/patternfly/patternfly1/epel-${DISTRIBUTION_VERSION}-x86_64" \
                --lookaside check-updates-"${distid}" \
                --lookaside check-extras-"${distid}" \
                --lookaside centos-ovirt36-"${distid}" \
                --lookaside check-epel-"${distid}" \
                --lookaside centos-glusterfs37-"${distid}" \
                --lookaside check-base-"${distid}" \
                --lookaside check-patternfly-"${distid}" \
                --repoid check-custom-"${distid}"
        else
            repoclosure \
                --tempcache \
                --repofrompath=check-custom-"${distid}","${CUSTOM_URL}" ${STATIC_RP} \
                --repofrompath=check-base-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/os/x86_64/ \
                --repofrompath=check-updates-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/updates/x86_64/ \
                --repofrompath=check-extras-"${distid}","${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/extras/x86_64/ \
                --repofrompath=check-epel-"${distid}","${EPEL_MIRROR}"/epel/"${DISTRIBUTION_VERSION}"/x86_64/ \
                --repofrompath=check-glusterfs-epel-"${distid}","${GLUSTER_MIRROR}"/pub/gluster/glusterfs/LATEST/EPEL.repo/epel-"${DISTRIBUTION_VERSION}"/x86_64/ \
                --repofrompath=check-glusterfs-epel-noarch-"${distid}","${GLUSTER_MIRROR}"/pub/gluster/glusterfs/LATEST/EPEL.repo/epel-"${DISTRIBUTION_VERSION}"/noarch \
                --repofrompath=check-jpackage-generic-"${distid}","${JPACKAGE_MIRROR}"/jpackage/6.0/generic/free \
                --repofrompath=check-patternfly-"${distid}","${COPR}/patternfly/patternfly1/epel-6-x86_64" \
                --lookaside check-updates-"${distid}" \
                --lookaside check-extras-"${distid}" \
                --lookaside check-epel-"${distid}" \
                --lookaside check-glusterfs-epel-"${distid}" \
                --lookaside check-glusterfs-noarch-epel-"${distid}" \
                --lookaside check-base-"${distid}" \
                --lookaside check-jpackage-rhel5-"${distid}" \
                --lookaside check-jpackage-generic-"${distid}" \
                --lookaside check-patternfly-"${distid}" \
                --repoid check-custom-"${distid}"
        fi
    elif [ "${DISTRIBUTION}" == "fc" ] \
        || [ "${DISTRIBUTION}" == "Fedora" ]; then
        repoclosure \
            --tempcache \
            --repofrompath=check-custom-"${distid}","${CUSTOM_URL}" ${STATIC_RP} \
            --repofrompath=check-fedora-"${distid}","${FEDORA_MIRROR}"/fedora/releases/"${DISTRIBUTION_VERSION}"/Everything/x86_64/os/ \
            --repofrompath=check-updates-"${distid}","${FEDORA_MIRROR}"/fedora/updates/"${DISTRIBUTION_VERSION}"/x86_64/ \
            --repofrompath=check-updates-testing-"${distid}","${FEDORA_MIRROR}"/fedora/updates/testing/"${DISTRIBUTION_VERSION}"/x86_64/ \
            --repofrompath=check-patternfly-"${distid}",""${COPR}/patternfly/patternfly1/fedora-${DISTRIBUTION_VERSION}-x86_64"" \
            --lookaside check-fedora-"${distid}" \
            --lookaside check-updates-"${distid}" \
            --lookaside check-updates-testing-"${distid}" \
            --lookaside check-patternfly-"${distid}" \
            --repoid check-custom-"${distid}"
    fi
}

main() {
    get_opts "${@}"
    validation
    check_layout
    check_repo_closure
}

main "${@}"
