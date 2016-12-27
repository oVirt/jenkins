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

# move the exported artifacts to jenkins workspace, as they are created in the
# project root
mkdir -p "$WORKSPACE"/exported-artifacts
sudo chown -R "$USER:$USER" "$WORKSPACE/exported-artifacts"
if ls "$WORKSPACE/$project/exported-artifacts/"* &>/dev/null; then
    sudo mv "$WORKSPACE/$project/exported-artifacts/"* \
            "$WORKSPACE/exported-artifacts/"
    sudo rmdir "$WORKSPACE/$project/exported-artifacts/"
fi
exit 0
