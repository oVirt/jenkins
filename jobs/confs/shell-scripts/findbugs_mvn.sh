#!/bin/bash
echo "shell-scripts/findbugs_mvn.sh"

pushd ovirt-engine
mvn \
    clean \
    install \
    findbugs:findbugs \
    -DskipTests \
    -U \
    -s "$WORKSPACE"/jenkins/xml/artifactory-ovirt-org-settings.xml \
    -Dmaven.repo.local="$WORKSPACE"/.m2