FROM quay.io/pod_utils/jenkins-caching-virtualization-agent:1.0.5

RUN yum install -y mock
COPY systemd/* /etc/systemd/system/
RUN systemctl enable var-cache-mock.mount var-lib-mock.mount var-lib-lago.mount
RUN echo "jenkins        ALL=(ALL)       NOPASSWD: ALL" >> /etc/sudoers
