#!/bin/bash -x
echo "shell-scripts/ovirt-engine_upgrade-db.cleanup.sh"

DBNAME="${{JOB_NAME//[\/=]/_}}_${{BUILD_NUMBER}}"
echo "Dropping db  ${{DBNAME}}"
sudo -u postgres dropdb "$DBNAME"
