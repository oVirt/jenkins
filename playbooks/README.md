STDCI Automated deployment playbooks
====================================

This directory contains Ansible playbooks and additional files needed to
automatically setup STDCI Jenkins masters in OpenShift

Running the playbooks found here
--------------------------------

You would need to have Ansible installed as well as some other
prerequisites, see below for how to install them.

Each playbook should typically contain header comments including details
about how to run it. Most playbooks typically assume you already have
the `oc` tool installed and available in `$PATH`, and that you've used
it to log into the OpenShift account and namespace where you want to
have things deployed.

Files in this directory
-----------------------

Here is a brief list of the fils found here and their purpose.

File               | What it does
------------------ | ---------------------------------------------------
inventories/       | Contains Ansible inventory files
roles/             | Contains Ansible roles used in the playbooks
README.md          | You're reading it right now
master_deploy.yaml | Deploys jenkins masters into OpenShift
slaves_deploy.yaml | Sets up container slaves in OpenShift

Installing Ansible and Python prerequisites
-------------------------------------------

All the code found here had been developed and tested using Python 3.
But not every Python 3 version is supported.

### Installing the right version of Python

On CentOS or RHEL 7.x you can use [Python 3.6.3 which is shipped in
SCL][1]. To install it either use the instructions in the mentioned link
or, if you don't want to use Subscription Manager on RHEL, just add the
following `*.repo` file to `/etc/yum.repos.d`:

    [centos-sclo-rh]
    name=CentOS-7 - SCLo rh
    baseurl=http://mirror.centos.org/centos/7/sclo/$basearch/rh/
    gpgcheck=1
    enabled=1
    gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-SIG-SCLo

After adding it you can proceed to installing Python:

    yum isntall rh-python36 rh-python36-python-pip \
        rh-python36-python-virtualenv

On Fedora you need to install Python 3.5 as the Python 3.6 version
shipped with it is incompatible with some Python libraries Ansible uses.

    dnf install python3.5.6

### Setting up a Python virtualenv

To create and manage a Python 3 virtualenv, its recommended to install
`virtualenvwrapper` and all further instractions assume that you did. To
install it simply run:

    yum isntall virtualenvwrapper

Or on Fedora:

    dnf install virtualenvwrapper

After installing it you'll need to logoff and logon to you shell session
to have it activated.

Once you have `virtualenvwrapper` installed, you can use the following
commands to setup the virtualenv in CentOS (assuming you are running
them from the root of this Git repo):

    mkvirtualenv stdci_deploy \
        -p $(cat automation/check-patch.master_deploy.python)
    pip install -U pip
    pip install -r automation/check-patch.playbooks.requirements.lock

On Fedora the setup is slightly different:

    mkvirtualenv stdci_deploy -p python3.5
    pip install -r automation/check-patch.playbooks.requirements.lock

Once the installation is done you are ready to run Ansible from the
virtualenv you just created. If you exit the shell or turn of the laptop
you can re-activate it with the following command:

    workon stdci_deploy

To deactivate it you can use:

    deactivate

[1]: https://www.softwarecollections.org/en/scls/rhscl/rh-python36/
