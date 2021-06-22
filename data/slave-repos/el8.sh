sudo dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
packages_list=(
    java-11-openjdk-headless git python3-pyyaml python3-pyxdg python3-six
    python3-py python3-jinja2 python3
    firewalld haveged libvirt qemu-kvm python3-paramiko
    libselinux-utils kmod rpm-plugin-selinux
)
sudo dnf -y install "${packages_list[@]}"
cat << EOF > /etc/modprobe.d/nested.conf
options kvm-intel nested=y
EOF

# Add the credentials ssh keys.
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDQipypSdCjrHfL83jFSQvjIpcnNjvvLHC7K9nyxwg5n+j3JYlYwvW5VvolCZ/1JnKB8FkjAo49Zw7Cqf/RrnXTvE1cqEnCBRWWj29BBt0rfVTHKBLgN39gV7KYnbkV30WtBdGAI7rP5Hu9ywJ8RGhZ5YXQbwgDHBMYE/8PqYe4dN7ZRNU1FOXrY/Y6JfPMaie8h/coYtgKrThkYPRG41ku5KPdF/xnfcWBINB/jp1mGDmr1P/GA+/68PHt3W2KnsBjuqnbegk2kNNqK8fVtWZIE5Y53SGJqjP2y6He3dW7VicR3Snkdzm4bCcO+Mvo8tMLJhjX4fZFUbqNfZvVmcWr Generated-by-Nova" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
alternatives --set python /usr/bin/python3
