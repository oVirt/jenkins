#!/bin/bash -e
echo "scripts/whitelist_filter.sh"
#
# Fails the build if it was triggered by a non-whitelisted commiter
#

# Check whitelist

if [[ -z "$GERRIT_WHITELIST_REPO" ]]; then
    echo "Whitelist for Grrit contributors not defined for this"
    echo "instance, everyone can make CI run!"
    exit 0
fi

git init jenkins-whitelist
echo "Fetching whitelist repo from ${GERRIT_WHITELIST_REPO}..."
cd jenkins-whitelist
git fetch "$GERRIT_WHITELIST_REPO" +refs/heads/master:myhead

if [[ -z "$GERRIT_PATCHSET_UPLOADER_EMAIL" ]]; then
    echo "This script is designed to verify gerrit events only."
    exit 0
elif git cat-file -p myhead:jenkins-whitelist.txt | \
        grep -E -q -e "^$GERRIT_PATCHSET_UPLOADER_EMAIL\$"; then
    exit 0
fi
exit 1
