#!/bin/bash -x
echo "shell-scripts/ovirt-engine_upgrade-engine.cleanup.sh"
#
# Parameters:
#
# version
#
#   version to upgrade to
#


VERSION="{version}"

sudo puppet agent --enable
sudo "$WORKSPACE/jenkins/jobs/ovirt-engine_upgrade_to_${{VERSION}}/cleanup.sh" \
    --workspace="$WORKSPACE" \
    --cleanup-file="$WORKSPACE/jenkins/jobs/ovirt-engine_upgrade_to_${{VERSION}}/cleanup.file.otopi"
sudo chown -R jenkins:jenkins "$WORKSPACE"