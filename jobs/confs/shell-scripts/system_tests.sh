#!/bin/bash -xe
echo "shell-scripts/system_tests.sh"

WORKSPACE=$PWD

OVIRT_CONTRIB="/usr/share/ovirtlago"
VIRT_CONFIG="${OVIRT_CONTRIB}/config/virt/centos7.json"
REPOSYNC_YUM_CONFIG="${OVIRT_CONTRIB}/config/repos/ovirt-3.5.repo"
STORE_CONFIG="${OVIRT_CONTRIB}/config/stores/ci.json"
ANSWER_FILE="${OVIRT_CONTRIB}/config/answer-files/el6_3.5.conf"

PREFIX="${WORKSPACE}/lago-prefix"

chmod g+x "${WORKSPACE}"

rm -rf "$PREFIX"
# Create $PREFIX for current run
lagocli init \
    "${PREFIX}" \
    "${VIRT_CONFIG}" \
    --template-repo-path="$STORE_CONFIG"
cd "${PREFIX}"

echo '[INIT_OK] Initialized successfully, will need cleanup later'

# Fetch RPMs
lagocli ovirt reposetup \
    --reposync-yum-config="${REPOSYNC_YUM_CONFIG}"

# Start VMs
lagocli start

# Install RPMs
lagocli ovirt deploy

lagocli ovirt engine-setup \
    --config="${ANSWER_FILE}"

# Start testing
res=0
lagocli ovirt runtest \
    "${OVIRT_CONTRIB}/test_scenarios/bootstrap_3_5.py" \
|| res=$?
lagocli ovirt collect \
    --output "${PREFIX}/test_logs/post_bootstrap"
if [[ "$res" != "0" ]]; then
    exit $res
fi

lagocli ovirt runtest \
    "${OVIRT_CONTRIB}/test_scenarios/create_clean_snapshot.py" \
&& lagocli ovirt runtest \
    "${OVIRT_CONTRIB}/test_scenarios/basic_sanity.py" \
|| res=$?
lagocli ovirt collect \
    --output "${PREFIX}/test_logs/post_basic_sanity"
if [[ "$res" != "0" ]]; then
    exit $res
fi
