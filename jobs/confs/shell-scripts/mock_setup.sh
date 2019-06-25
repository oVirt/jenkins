#!/bin/bash -xe
echo "shell-scripts/mock_setup.sh"
shopt -s nullglob

# cleanup and setup env
if [[  "$CLEAN_CACHE" == "true" ]]; then
    sudo -n rm -Rf /var/cache/mock
fi

# Make sure the cache has a newer timestamp than the config file or it will
# not be used
sudo -n touch /var/cache/mock/*/root_cache/cache.tar.gz 2>/dev/null || :
# Make sure yum caches are clean
sudo -n yum clean all || :
exit 0
