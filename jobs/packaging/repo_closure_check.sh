#!/bin/sh

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

LAYOUT=""
BASE_URL="http://resources.ovirt.org"
CENTOS_MIRROR="http://centos.mirror.constant.com/"
EPEL_MIRROR="http://linux.mirrors.es.net/"
FEDORA_MIRROR="http://mirrors.kernel.org/"
GLUSTER_MIRROR="http://download.gluster.org/"
JPACKAGE_MIRROR="ftp://jpackage.hmdc.harvard.edu/"

die() {
	local m="${1}"
	echo "FATAL: ${m}"
	exit 1
}

usage() {
	cat << __EOF__
    ${0} [options]
    --distribution             - Distribution you want to test
    --layout                   - Layout you want to use [old, new]
    --repo                     - Repository you want to test
    --distribution-version     - Distribution version (6,19)

    Example:
	new layout:
    ${0} --distribution=fc --layout=new --distribution-version=20 --repo=test-repo
    ${0} --distribution=el --layout=new --distribution-version=6 --repo=test-repo

    old layout:
    ${0} --distribution=Fedora --layout=old --distribution-version=20 --repo=test-repo
    ${0} --distribution=EL --layout=old --distribution-version=6 --repo=test-repo
__EOF__
}

get_opts() {
	while [ -n "${1}" ]; do
		opt="${1}"
		v="${opt#*=}"
		shift
		case "${opt}" in
			--repo=*)
				REPO_NAME="${v}"
				;;
			--distribution=*)
				DISTRIBUTION="${v}"
				;;
			--distribution-version=*)
				DISTRIBUTION_VERSION="${v}"
				;;
			--layout=*)
				LAYOUT="${v}"
				;;
			*)
				usage
				die "Wrong option"
				;;
		esac
	done
}

validation() {
	[ -n "${DISTRIBUTION}" ] || die "Please specify --distribution= option"
	[ -n "${REPO_NAME}" ] || die "Please specify --repo= option"
	[ -n "${DISTRIBUTION_VERSION}" ] || die "Please specify --distribution-version= option"
	[ -n "${LAYOUT}" ] || die "Please specify --layout= option"
}

check_layout() {
	local dist
	if [ "${LAYOUT}" = "new" ]; then
		repo="${DISTRIBUTION}${DISTRIBUTION_VERSION}"
		BASE_URL="${BASE_URL}/pub"
	elif [ "${LAYOUT}" = "old" ]; then
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
}

check_repo_closure() {
	if [ "${DISTRIBUTION}" = "el" ] \
		|| [ "${DISTRIBUTION}" = "Centos" ]; then
		custom_url="${BASE_URL}/${REPO_NAME}/rpm/${repo}"
		repoclosure \
			-t \
			--repofrompath=check-custom,"${custom_url}" \
			--repofrompath=check-base,"${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/os/x86_64/ \
			--repofrompath=check-base-i386,"${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/os/i386/ \
			--repofrompath=check-updates,"${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/updates/x86_64/ \
			--repofrompath=check-extras,"${CENTOS_MIRROR}/${DISTRIBUTION_VERSION}"/extras/x86_64/ \
			--repofrompath=check-epel,"${EPEL_MIRROR}"/fedora-epel/"${DISTRIBUTION_VERSION}"/x86_64/ \
			--repofrompath=check-glusterfs-epel,"${GLUSTER_MIRROR}"/pub/gluster/glusterfs/LATEST/EPEL.repo/epel-6/x86_64/ \
			--repofrompath=check-glusterfs-epel-noarch,"${GLUSTER_MIRROR}"/pub/gluster/glusterfs/LATEST/EPEL.repo/epel-6.4/noarch \
			--repofrompath=check-jpackage-generic,"${JPACKAGE_MIRROR}"/JPackage/6.0/generic/free \
			-l check-updates \
			-l check-extras \
			-l check-epel \
			-l check-glusterfs-epel \
			-l check-glusterfs-noarch-epel\
			-l check-base \
			-l check-base-i386 \
			-l check-jpackage-rhel5 \
			-l check-jpackage-generic \
			-r check-custom
	elif [ "${DISTRIBUTION}" = "fc" ] \
		|| [ "${DISTRIBUTION}" = "Fedora" ]; then
		custom_url="${BASE_URL}/${REPO_NAME}/rpm/${repo}"
		repoclosure \
			-t \
			--repofrompath=check-custom,"${custom_url}" \
			--repofrompath=check-fedora,"${FEDORA_MIRROR}"/fedora/releases/"${DISTRIBUTION_VERSION}"/Everything/x86_64/os/ \
			--repofrompath=check-updates,"${FEDORA_MIRROR}"/fedora/updates/"${DISTRIBUTION_VERSION}"/x86_64/ \
			--repofrompath=check-updates-testing,"${FEDORA_MIRROR}"/fedora/updates/testing/"${DISTRIBUTION_VERSION}"/x86_64/ \
			-l check-fedora \
			-l check-updates \
			-l check-updates-testing \
			-r check-custom
	fi
}

main() {
	get_opts "${@}"
	validation
	check_layout
	check_repo_closure
}

main "${@}"
