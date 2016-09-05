#!/bin/bash -x
echo "shell-scripts/repos-check-closure_run-check.sh"

function print_err(){{
  local errmsg="$1"
  echo "ERROR: ${{errmsg}}"
}}

# Run repo_closure_check.sh for each distro
DISTRO_REGEX='^([a-z]{{2}})([0-9]+)$'
echo "########## Running repo_closure_check.sh for ${{DISTRIBUTION}} ##########"
if [[ ${{DISTRIBUTION}} =~ ${{DISTRO_REGEX}} ]]; then
    # prepare the parameters for repo_closure_check.sh script
    DIST_NAME=${{BASH_REMATCH[1]}}
    VER=${{BASH_REMATCH[2]}}
    "${{USE_STATIC}}" && STATIC_SETTINGS="--static-repo=${{STATIC_REPO}}"
    "${{USE_EXPERIMENTAL}}" &&
        EXP_SETTINGS="--experimental-repo=${{EXPERIMENTAL_REPO}}"
    [[ "${{CLEAN_METADATA}}" == "true" ]] && rm -rf "${{WORKSPACE}}"/check-*

    # create a temp script that will call the repo_closure_check.sh in mock
    cd jenkins
    cat <<EOT > run_script_for_repoclosure.sh
#!/bin/bash -ex
./jobs/packaging/repo_closure_check.sh \
--distribution="${{DIST_NAME}}" \
--layout=new \
--distribution-version="${{VER}}" \
--repo="${{REPO_NAME}}" \
"${{STATIC_SETTINGS}}" "${{EXP_SETTINGS}}" || :
exit 0
EOT
    cat <<EOT > run_script_for_repoclosure.packages
yum-utils
EOT
    ./mock_configs/mock_runner.sh \
    --mock-confs-dir mock_configs/ \
    --execute-script run_script_for_repoclosure.sh \
    --try-proxy \
    fc24
else
    print_err "Distribution name '${{DISTRIBUTION}}' not supported"
fi
