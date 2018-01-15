#!/bin/bash -e
echo "scripts/whitelist_filter.sh"
#
# Fails the build if it was triggered by a non-whitelisted commiter
#

# Check whitelist

WHITELIST_REPO="https://gerrit.ovirt.org/jenkins-whitelist"

git init jenkins-whitelist
echo "Fetching whitelist repo from ${WHITELIST_REPO}..."
cd jenkins-whitelist
git fetch "$WHITELIST_REPO" +refs/heads/master:myhead

if [[ -z "$GERRIT_PATCHSET_UPLOADER_EMAIL" ]]; then
    echo "This script is designed to verify gerrit events only."
    exit 0
elif git cat-file -p myhead:jenkins-whitelist.txt | \
        grep -E -q -e "^$GERRIT_PATCHSET_UPLOADER_EMAIL\$"; then
    exit 0
fi
exit 1
