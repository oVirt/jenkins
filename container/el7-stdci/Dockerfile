FROM local/el7-systemd-jenkins-slave-base

LABEL "org.ovirt.gerrit.jenkins.stdci"=""
ARG username="jenkins"
ARG lago_version="0.44.0"

RUN rm -rf /etc/yum.repos.d/*
COPY repos/* /etc/yum.repos.d/
RUN \
    yum install -y epel-release centos-release-qemu-ev &&\
    yum install -y git mock sed bash procps-ng createrepo python-paramiko \
        PyYAML python2-pyxdg python-jinja2 python-py python34-PyYAML \
        docker lago-${lago_version}
COPY sbin/export_environment.sh /usr/sbin/export_environment
COPY systemd/* /etc/systemd/system/
COPY sudoers.d/* /etc/sudoers.d/
COPY deploy.sh /usr/local/bin/deploy
RUN chmod +x /usr/local/bin/deploy
RUN deploy
WORKDIR /home/$username
