#!/bin/bash
echo "shell-scripts/whitelist-filter.sh"
#
# Fails the build if it was triggered by a non-whitelisted commiter
#

# Check whitelist
if ! [[ -z "$GERRIT_PATCHSET_UPLOADER_EMAIL" ]] \
    && [[ "@redhat.com" != "${GERRIT_PATCHSET_UPLOADER_EMAIL: -11}" ]] \
    && ! egrep -q \
             -e "^$GERRIT_PATCHSET_UPLOADER_EMAIL\$" \
             jenkins-whitelist/jenkins-whitelist.txt; then
   echo "USER $GERRIT_PATCHSET_UPLOADER_EMAIL NOT FOUND IN THE WHITELIST, NOT RUNNING"
   exit 1
fi
