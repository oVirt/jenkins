#!/bin/bash -xe
# remove chroot to free space
sudo rm -Rf mock mock-cache
# compress logs
pushd "$WORKSPACE"/exported-artifacts
shopt -s nullglob
tar cvjf logs.tbz *log *_pkgs "$WORKSPACE"/*log
rm -f *log *_pkgs
