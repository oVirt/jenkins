#!/bin/bash -xe
echo "shell-scripts/mock_cleanup.sh"
# remove chroot to free space
sudo rm -Rf mock mock-cache
# remove mock system cache, we will setup proxies to do the caching and this
# takes lots of space between runs
sudo rm -Rf /var/cache/mock/*
# compress logs
pushd "$WORKSPACE"/exported-artifacts
shopt -s nullglob
tar cvjf logs.tbz *log *_pkgs "$WORKSPACE"/*log
rm -f *log *_pkgs
