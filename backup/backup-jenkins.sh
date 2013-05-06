#!/bin/bash

JENKINS_DIR=/var/lib/jenkins
BACKUP_DIR=/backups
DAILY_BACKUPS_TO_KEEP=30

if [[ ! -d "${BACKUP_DIR}" ]]; then
    mkdir -p "${BACKUP_DIR}" \
         && chown jenkins.jenkins "${BACKUP_DIR}"
fi

JENBAKLISTFILE="$(mktemp --tmpdir="${BACKUP_DIR}" jenkins-backuplistfile.XXXXX)" \
                || { echo "Unable to create temporary file."; exit 1; }


pushd "${JENKINS_DIR}"
find -maxdepth 1 -type f -name "*.xml" > "${JENBAKLISTFILE}"
find users \
     userContent \
     plugins >> "${JENBAKLISTFILE}"
find -H jobs -maxdepth 2 -name "config.xml" -type f >> "${JENBAKLISTFILE}"
tar czvf "${BACKUP_DIR}"/jenkins-backup-$(date +"%Y-%m-%d_%H_%M_%S").tgz -T "${JENBAKLISTFILE}"
popd

find "${BACKUP_DIR}" \
              -type f \
              -mtime +${DAILY_BACKUPS_TO_KEEP} \
              -exec rm -f {} +
