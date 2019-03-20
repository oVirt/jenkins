FROM quay.io/pod_utils/jenkins-caching-virtualization-agent:1.0.6

RUN yum install -y mock
COPY systemd/* /etc/systemd/system/
RUN systemctl enable var-cache-mock.mount var-lib-mock.mount var-lib-lago.mount
RUN echo "#includedir /etc/sudoers.d" >> /etc/sudoers
COPY etc/sudoers.d/* /etc/sudoers.d/
RUN echo _CI_ENV_.* >> /etc/export_list
RUN systemctl enable \
    var-cache-mock.mount \
    var-lib-mock.mount \
    var-lib-lago.mount \
    remount-sys.service \
    && sed -Ei 's,(^mock.*$),\1jenkins,g' /etc/group
