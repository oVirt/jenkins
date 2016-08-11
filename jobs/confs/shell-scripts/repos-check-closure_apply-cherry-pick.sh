## apply cherry-pick
PATCHES_ARR=( ${PATCHES//,/ } )
cd "${WORKSPACE}/jenkins"
for patch in "${PATCHES_ARR[@]}"; do
    echo "cherry-picking patch: ${patch}"
    git fetch git://gerrit.ovirt.org/jenkins ${patch} && git cherry-pick FETCH_HEAD
done
