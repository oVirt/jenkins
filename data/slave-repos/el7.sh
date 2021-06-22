yum -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
pkg_list=(epel-release java-1.8.0-openjdk-headless kernel gdbm glibc sssd systemd git mock PyYAML python2-pyxdg python2-six \
python-paramiko PyYAML python2-pyxdg python-jinja2 python-py python-six python36-PyYAML python36-pyxdg rpm-libs haveged libvirt \
qemu-kvm nosync libselinux-utils kmod)

yum -y install "${pkg_list[@]}"

cat << EOF > /etc/modprobe.d/nested.conf
options kvm-intel nested=y
EOF

cat << EOF > /etc/security/limits.d/10-nofile.conf
* soft nofile 64000
* hard nofile 96000
EOF

cat << EOF > /etc/selinux/config
SELINUX=permissive
SELINUXTYPE=targeted
EOF

chmod 0644 /etc/modprobe.d/nested.conf /etc/security/limits.d/10-nofile.conf /etc/selinux/config

# Add the credentials ssh keys.
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDQipypSdCjrHfL83jFSQvjIpcnNjvvLHC7K9nyxwg5n+j3JYlYwvW5VvolCZ/1JnKB8FkjAo49Zw7Cqf/RrnXTvE1cqEnCBRWWj29BBt0rfVTHKBLgN39gV7KYnbkV30WtBdGAI7rP5Hu9ywJ8RGhZ5YXQbwgDHBMYE/8PqYe4dN7ZRNU1FOXrY/Y6JfPMaie8h/coYtgKrThkYPRG41ku5KPdF/xnfcWBINB/jp1mGDmr1P/GA+/68PHt3W2KnsBjuqnbegk2kNNqK8fVtWZIE5Y53SGJqjP2y6He3dW7VicR3Snkdzm4bCcO+Mvo8tMLJhjX4fZFUbqNfZvVmcWr Generated-by-Nova" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
#Remove MAC address to avoid boot failure for instances created from this template
sed -i '/^HWADDR/d' /etc/sysconfig/network-scripts/ifcfg-*

#systemctl start ovirt-guest-agent
#systemctl enable ovirt-guest-agent
systemctl mask cloud-init-local
systemctl mask cloud-init
