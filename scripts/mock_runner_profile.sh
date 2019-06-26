# mock_runner_profile.sh - Shell profile for mock_runner
#                          This file is injected by mock_runner.sh to
#                          run at shell startup
#

_ci_ssh_prep() {
    # copy files from /var/lib/ci_ssh_files to /root/.ssh
    install -o root -m 700 -d /root/.ssh
    install -o root -m 600 -t /root/.ssh /var/lib/ci_ssh_files/*

    # Set default SSH user to $SSH_AUTH_USER with fall back to
    # $MOCK_EXTERNAL_USER
    local ssh_config=/root/.ssh/config
    local ssh_user="${SSH_AUTH_USER:-$MOCK_EXTERNAL_USER}"
    if [[ $ssh_user ]]; then
        echo "User $ssh_user" > "$ssh_config"
        chmod 400 "$ssh_config"
    fi
}

_setup_path() {
    export PATH="/var/lib/ci_toolbox:${PATH}"
}

_setup_path
_ci_ssh_prep
# Remove functions to leave shell namespace clean
unset _ci_ssh_prep _setup_path
