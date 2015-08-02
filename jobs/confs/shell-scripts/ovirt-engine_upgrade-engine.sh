#!/bin/bash -xe
echo "shell-scripts/ovirt-engine_upgrade-engine.sh"
#
# Parameters:
#
# version
#
#   version to upgrade to
#

VERSION="{version}"

### Create rpm and repository
sudo chown -R jenkins:jenkins "$WORKSPACE"
rm -Rf logs
mkdir -p logs
tmp_repo="$WORKSPACE/tmp_repo"
[[ -e "$tmp_repo" ]] && rm -rf "$tmp_repo"
mkdir -p "$tmp_repo"
"$WORKSPACE/jenkins/jobs/ovirt-engine_upgrade_to_${{VERSION}}/build_engine_rpm.sh" \
    --src-dir "$WORKSPACE"/ovirt-engine \
    --dst-dir "$tmp_repo" \
    --mvn-settings "$WORKSPACE"/artifactory-ovirt-org-settings.xml
createrepo "$tmp_repo"

#### Test the upgrade
sudo "$WORKSPACE/jenkins/jobs/ovirt-engine_upgrade_to_${{VERSION}}/upgrade.sh" \
    --workspace="$WORKSPACE" \
    --cleanup-file="$WORKSPACE/jenkins/jobs/ovirt-engine_upgrade_to_${{VERSION}}/cleanup.file.otopi" \
    --setup-file="$WORKSPACE/jenkins/jobs/ovirt-engine_upgrade_to_${{VERSION}}/setup.file.otopi" \
    --repo-to="${{REPOS_TO:+$REPOS_TO,}}file://$tmp_repo" \
    --repo-from="$REPOS_FROM"