#!/bin/bash -x
# ./ovirt_engine_upgrade_stable_32_to_latest_32.sh <workspace> <RPMS location>

WORKSPACE=$1
JOB_NAME=ovirt_engine_upgrade_stable_32_to_latest_32
ANS_FILE=${WORKSPACE}/jenkins/jobs/"${JOB_NAME}"/answer.file
REPO_FILE=${WORKSPACE}/jenkins/jobs/"${JOB_NAME}"/"${JOB_NAME}".repo
RPMS_DIR=$2
PROJECT_DIR=${WORKSPACE}/ovirt-engine
DATE=$(date | tr  ' :' '_')
LOG=${WORKSPACE}/${DATE}.log

validate()
{
	if [[ -z "$WORKSPACE"  \
		|| -z "$RPMS_DIR" ]]; then
		echo "Please provide 2 parameters to the job"
		exit 1
	fi

	if [[ ! -f "$ANS_FILE" ]]; then
		echo "$ANS_FILE does not exist"
		exit 1
	fi

}

pre_clean()
{
	echo "----- Cleaning old rpms... ----"
	if rpm -q ovirt-engine; then
		sudo engine-cleanup -u
		sudo yum -y remove ovirt-engine
	fi
	sudo yum -y remove $(rpm -qa | grep ovirt)
        #sudo rm -f /usr/lib/systemd/system/ovirt-engine.service || :
	rm -f "${WORKSPACE}"/*log
}


configure_repo()
{
	createrepo "${RPMS_DIR}"
# Configuring the repo
cat > /tmp/tmp_update_repo.repo << EOF
[update-repo]
name=update repo
baseurl=file://${RPMS_DIR}
enabled=1
gpgcheck=0
EOF

	sudo cp /tmp/tmp_update_repo.repo /etc/yum.repos.d
	rm -f /tmp/tmp_update_repo.repo
}

copy_setup_log()
{
	SETUP_LOG=$(grep 'log$' /tmp/engine-setup.log | sed 's/^.*at: //')
	if [[ -f "${SETUP_LOG}" ]]; then
		cp -f "${SETUP_LOG}" "${WORKSPACE}"
	fi
}

copy_cleanup_log()
{
	CLEANUP_LOG=$(grep 'log$' /tmp/ovirt-cleanup.log | sed 's/^.*at //')
	if [[ -f "${CLEANUP_LOG}" ]]; then
		cp -f "${CLEANUP_LOG}" "${WORKSPACE}"
	fi
}

copy_upgrade_log()
{
	UPGRADE_LOG=$(grep 'log$' /tmp/engine-upgrade.log | sed 's/.*at //')
	if [[ -f "${UPGRADE_LOG}" ]]; then
		cp -f "${UPGRADE_LOG}" "${WORKSPACE}"
	fi
}

install_latest_32()
{
	sudo cp "${REPO_FILE}" /etc/yum.repos.d
	# Installing latest 3.2
	sudo yum -y install ovirt-engine
        #sudo rm -f /usr/lib/systemd/system/ovirt-engine.service || :

	# Running engine-setup
	sed -i '/HOST_FQDN=/d' "${ANS_FILE}"
	echo "HOST_FQDN=$(hostname)" >> "${ANS_FILE}"
	sudo engine-setup --answer-file="${ANS_FILE}" | tee /tmp/engine-setup.log
	if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
		echo "SETUP_FAILED" >> ${LOG}
		SETUP_LOG=$(grep ^Please /tmp/engine-setup.log \
			| grep -o '/[^ ]*\.log')
		if [[ -f "${SETUP_LOG}" ]]; then
			cp "${SETUP_LOG}" "${WORKSPACE}"
		fi
		exit 1
	fi
	copy_setup_log
}

configure_deps_repo()
{
	cat > /tmp/tmp_update_deps_repo.repo << EOF
[update-deps-repo]
name=update deps repo
baseurl=file://${WORKSPACE}/rpms
enabled=1
gpgcheck=0
EOF

	sudo cp /tmp/tmp_update_deps_repo.repo \
		/etc/yum.repos.d
	rm -f /tmp/tmp_update_deps_repo.repo
}

job()
{
	sudo yum -y update ovirt-engine-setup
	configure_deps_repo
	sudo engine-upgrade -u | tee /tmp/engine-upgrade.log
	if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
		echo "UPGRADE_FAILED" >> "${LOG}"
		UPGRADE_LOG=$(grep ^please /tmp/engine-upgrade.log \
				| grep -o '/[^ ]*\.log')
		if [[ -f "${UPGRADE_LOG}" ]]; then
			cp -f "${UPGRADE_LOG}" "${WORKSPACE}"
		fi
	fi
	copy_upgrade_log
	echo "" >> ${LOG}
}

post_clean()
{
    # Cleanup stage
	rm -rf "${RPMS_DIR}"
	rm -f /tmp/setup_"${DATE}" /tmp/upgrade_"${DATE}"
	sudo rm -f /etc/yum.repos.d/tmp_update_repo.repo \
		"${JOB_NAME}".repo \
		/etc/yum.repos.d/tmp_update_deps_repo.repo
	sudo engine-cleanup -u | tee /tmp/ovirt-cleanup.log
	copy_cleanup_log
	sudo yum -y remove $(rpm -qa | grep ovirt)
}

disable_ovirt_repos()
{
	sudo sed -i 's/enabled=1/enabled=0/' $(grep -il 'ovirt-nightly' /etc/yum.repos.d/*)
}

enable_ovirt_repos()
{
	sudo sed -i 's/enabled=0/enabled=1/' $(grep -il 'ovirt-nightly' /etc/yum.repos.d/*)
}


main()
{
	validate
	pre_clean
	disable_ovirt_repos
	install_latest_32
	configure_repo
	job
	post_clean
	enable_ovirt_repos
}

main
