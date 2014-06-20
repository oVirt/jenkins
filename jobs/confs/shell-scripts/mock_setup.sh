#!/bin/bash -xe
# shell-scripts/mock_setup.sh
# cleanup and setup env
if [[  "$CLEAN_CACHE" == "true" ]]; then
    sudo rm -Rf /var/cache/mock
fi
sudo rm -Rf mock mock-cache exported-artifacts
mkdir -p mock exported-artifacts
chgrp mock mock "$WORKSPACE" "$WORKSPACE"/exported-artifacts
chmod g+rws mock

# Make sure the cache has a newer timestamp than the config file or it will
# not be used
sudo touch /var/cache/mock/*/root_cache/cache.tar.gz || :
exit 0
