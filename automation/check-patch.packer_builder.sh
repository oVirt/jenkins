#!/usr/bin/env bash
set -x
source /etc/os-release
os="${ID:?}${VERSION_ID:?}"
if [[ $NAME =~ 'Stream' ]]; then
    os="centos8-stream"
fi
rm -rf /etc/resolv.conf
tee -a /etc/resolv.conf > /dev/null <<EOT
nameserver 10.5.201.114
nameserver 10.5.201.75
EOT

OS_IMAGE_NAME="${os}-worker-image-$(date +%Y_%m_%d_%H_%M_%S)"
BASE_IMAGE=$(jq -r '.source_image' data/slave-repos/${os}.json)
SCRIPT=$(jq -r '.script' data/slave-repos/${os}.json)
# inject "per OS" values into packer file
tmp=$(mktemp)
jq --arg a "$OS_IMAGE_NAME" '.builders[0].image_name = $a' packer.json > "$tmp" && cp -f "$tmp" packer.json
tmp=$(mktemp)
jq --arg a "$BASE_IMAGE" '.builders[0].source_image = $a' packer.json > "$tmp" && cp -f "$tmp" packer.json
tmp=$(mktemp)
jq --arg a "$SCRIPT" '.provisioners[0].script = $a' packer.json > "$tmp" && cp -f "$tmp" packer.json
# run packer
/usr/bin/packer version
/usr/bin/packer validate packer.json
/usr/bin/packer build packer.json