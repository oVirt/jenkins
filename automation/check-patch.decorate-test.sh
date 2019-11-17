#!/bin/bash -ex
# A testing script to run inside a container that is a part of a decorated POD
# that has source cloning and artifact collection services
#
echo "Hello from '$0'"!
echo "PWD is $PWD"

ls -la /exported-artifacts
echo "This is an artifact!" > /exported-artifacts/artifact1.txt
echo "This is another artifact!" > /exported-artifacts/artifact2.txt
ls -la /exported-artifacts
