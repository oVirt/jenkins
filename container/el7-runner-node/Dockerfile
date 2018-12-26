FROM nonameyet/jenkins-virtualization-jnlp-agent:0.0.1-2-g593bd3e

RUN yum install -y mock
COPY systemd/* /etc/systemd/system/
RUN systemctl enable var-cache-mock.mount var-lib-mock.mount var-lib-lago.mount