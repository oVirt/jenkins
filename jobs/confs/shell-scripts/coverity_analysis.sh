#!/bin/bash -xe
echo "shell-scripts/coverity_analysis.sh"

mkdir -p "${{WORKSPACE}}/tmp"
export TMPDIR="${{WORKSPACE}}/tmp"

MAVEN_OPTS="-XX:PermSize=512M "
MAVEN_OPTS+="-XX:MaxPermSize=1024m "
MAVEN_OPTS+="-Xms1024M -Xmx4096m "
MAVEN_OPTS+="-Djava.io.tmpdir=${{WORKSPACE}}/tmp "
MAVEN_OPTS+="-Dgwt.compiler.localWorkers=1 "
MAVEN_OPTS+="-Dgwt.logLevel=TRACE"
export MAVEN_OPTS

wget -N https://scan.coverity.com/download/java/linux64 \
    --post-data "token=YqBYeyDp2jPuC_uVz0Hdog&project=ovirt-engine" \
    -O coverity_tool.tgz
rm -rf "{{$WORKSPACE}}"/"cov-analysis-linux64-*"

tar -xvf  coverity_tool.tgz

projects="\
backend/manager/modules/aaa,\
backend/manager/modules/bll,\
backend/manager/modules/branding,\
backend/manager/modules/common,\
backend/manager/modules/compat,\
backend/manager/modules/dal,\
backend/manager/modules/root,\
backend/manager/modules/scheduler,\
backend/manager/modules/searchbackend,\
backend/manager/modules/utils,\
backend/manager/modules/vdsbroker,\
backend/manager/modules/auth-plugin,\
backend/manager/modules/builtin-extensions,\
backend/manager/modules/enginesso,\
backend/manager/modules/extensions-api-root,\
backend/manager/modules/extensions-manager,\
backend/manager/modules/nmicrobenchmarks,\
backend/manager/modules/restapi,\
backend/manager/modules/services,\
backend/manager/modules/uutils,
"
pushd ovirt-engine
../cov-analysis-linux64-*/bin/cov-build \
    --dir cov-int \
    mvn clean install \
        -DskipTests=true \
        -s ${{WORKSPACE}}/jenkins/xml/artifactory-ovirt-org-settings.xml \
        -Dmaven.repo.local=${{WORKSPACE}}/.repository
#--projects ${{projects}}
tar czvf ovirt-engine-cov.tgz cov-int
curl \
    --form project=ovirt-engine \
    --form token=YqBYeyDp2jPuC_uVz0Hdog \
    --form email=dfediuck@redhat.com \
    --form file=@ovirt-engine-cov.tgz \
    https://scan.coverity.com/builds?project=ovirt-engine
