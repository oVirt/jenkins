#!/bin/bash -x
echo "shell-scripts/repos-check-closure_run-check.sh"

function print_err(){
  local errmsg="$1"
  echo "ERROR: ${errmsg}"
}

# Remove existing logs and artifacts, and create exported-artifacts if needed
echo "########## Cleanup ##########"
rm -Rf "${WORKSPACE}"/*.log "${WORKSPACE}"/exported-artifacts/*
mkdir -p "${WORKSPACE}"/exported-artifacts


# Run repo_closure_check.sh for each distro
DISTRO_REGEX='^([a-z]{2})([0-9]+)$'
for DIST in ${DISTRIBUTIONS//,/ }; do
    echo "########## Running repo_closure_check.sh for ${DIST} ##########"
    LOGFILE="${WORKSPACE}/repo_closure_check.${DIST}.log"
    if [[ ${DIST} =~ ${DISTRO_REGEX} ]]; then
        DIST_NAME=${BASH_REMATCH[1]}
        VER=${BASH_REMATCH[2]}
        "${USE_STATIC}" && STATIC_SETTINGS="--static-repo=${STATIC_REPO}"
        "${USE_EXPERIMENTAL}" &&
            EXP_SETTINGS="--experimental-repo=${EXPERIMENTAL_REPO}"
        [[ "${CLEAN_METADATA}" == "true" ]] && rm -rf "${WORKSPACE}"/check-*
        "${WORKSPACE}"/jenkins/jobs/packaging/repo_closure_check.sh \
                 --distribution="${DIST_NAME}" \
                 --layout=new \
                 --distribution-version="${VER}" \
                 --repo="${REPO_NAME}" \
                 ${STATIC_SETTINGS} ${EXP_SETTINGS} |& tee "${LOGFILE}"
    else
      print_err "Distribution name '${DIST}' not supported" | tee "${LOGFILE}"
    fi
done

# Archive the logs
echo "########## Archiving logs ##########"
tar cvzf exported-artifacts/logs.tgz "${WORKSPACE}"/*.log
