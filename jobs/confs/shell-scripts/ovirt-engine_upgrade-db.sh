#!/bin/bash -xe
echo "shell-scripts/ovirt-engine_upgrade-db.sh"
#
# Parameters:
#
# test-branch
#   Branch that is being tested (the one that was not chekced out by jenkins)
#
# action
#   If we are upgrading from test-branch or to test-branch, accepts the strings
#   'to' and 'from'
#

TEST_BRANCH="{test-branch}"
ACTION="{action}"
ACTION="${{ACTION?No action passed}}"

cd "$WORKSPACE"/ovirt-engine

### get current HEAD ###
cur_head="$(git rev-parse HEAD)"

if [[ "$ACTION"  == 'from' ]]; then
    git reset --hard "origin/$TEST_BRANCH"
    git clean -dxf
fi

### create db #####
DBNAME="${{JOB_NAME//[\/=]/_}}_${{BUILD_NUMBER}}"

echo "INFO::CREATING DATABASE"
sudo -u postgres createdb \
    "$DBNAME" \
    -e \
    -E UTF8 \
    --lc-collate en_US.UTF8 \
    --lc-ctype en_US.UTF8 \
    -T template0 \
    -O engine \
> /dev/null
echo "INFO::DATABASE CREATED"

# make sure we have user and access

echo "INFO::POPULATING DATABASE"
./packaging/dbscripts/schema.sh \
    -c apply \
    -u engine \
    -d "$DBNAME"
echo "INFO::DATABASE POPULATED"

### upgrade ####
cd "$WORKSPACE"/ovirt-engine
if [[ "$ACTION"  == 'from' ]]; then
    git reset --hard "$cur_head"
else
    git reset --hard origin/"$TEST_BRANCH"
fi
git clean -dxf

echo "INFO::Verifying that upgrade script is re-entrant ..."
./packaging/dbscripts/schema.sh \
    -c apply \
    -u engine \
    -d "$DBNAME"

#Go back o original code, just in case
git reset --hard "$cur_head"
git clean -dxf

exit 0
