FROM local/el7-systemd-jenkins-slave-base

LABEL "org.ovirt.gerrit.jenkins.stdci"=""
ARG username="jenkins"
ARG lago_version="0.44.0"
ARG openjdk_version="1.8.0"

#RUN rm -rf /etc/yum.repos.d/*
#COPY repos/* /etc/yum.repos.d/
RUN \
    yum install -y epel-release centos-release-qemu-ev &&\
    yum install -y git mock sed bash procps-ng createrepo python-paramiko \
        PyYAML python2-pyxdg python-jinja2 python-py python34-PyYAML \
        docker firewalld daemonize sudo qemu-kvm-ev libvirt \
        java-${openjdk_version}-openjdk-headless which
COPY firewalld-services/* /etc/firewalld/services/
COPY sbin/export_environment.sh /usr/sbin/export_environment
COPY sbin/lock_on_slot.sh /usr/sbin/lock_on_slot
COPY sbin/agent_daemon.sh /agent_daemon
COPY systemd/* /etc/systemd/system/
COPY sudoers.d/* /etc/sudoers.d/
COPY deploy.sh /usr/local/bin/deploy
RUN curl https://jenkins.ovirt.org/jnlpJars/agent.jar \
    -o /agent.jar
RUN chmod +x /usr/local/bin/deploy
RUN deploy
WORKDIR /home/$username
