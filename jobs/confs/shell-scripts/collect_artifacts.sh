#!/bin/bash -ex
echo "shell-scripts/collect_artifacts.sh"
cat <<EOC
_______________________________________________________________________
#######################################################################
#                                                                     #
#                         ARTIFACT COLLECTION                         #
#                                                                     #
#######################################################################
EOC

project="{project}"
WORKSPACE="${{WORKSPACE:-$PWD}}"
exported_artifacts="$WORKSPACE/exported-artifacts"

# move the exported artifacts to jenkins workspace, as they are created in the
# project root
mkdir -p "$exported_artifacts"
if ls "$WORKSPACE/$project/exported-artifacts/"* &>/dev/null; then
    sudo mv "$WORKSPACE/$project/exported-artifacts/"* "$exported_artifacts"
    sudo rmdir "$WORKSPACE/$project/exported-artifacts/"
fi
sudo chown -R "$USER:$USER" "$exported_artifacts"

if [[ ! -e "$exported_artifacts/repodata" ]] &&
    find "$exported_artifacts" -type f -name '*.rpm' | grep -q .
then
    if [[ -e '/usr/bin/dnf' ]]; then
        sudo dnf install -y createrepo
    else
        sudo yum install -y createrepo
    fi
    createrepo "$exported_artifacts"
fi

exit 0
