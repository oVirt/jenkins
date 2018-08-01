#!/bin/bash -ex

main(){
    enable_firewalld_service
    enable_docker_service
    enable_environment_service
    enable_jenkins_home_service
    enable_jnlp_slave
}

enable_firewalld_service() {
    local service_name
    for firewalld_service in /etc/firewalld/services/*; do
        service_name="${firewalld_service%%.*}"
        service_name="${service_name##*/}"
        firewall-offline-cmd --zone=public -q \
            --add-service="${service_name}"
    done
    systemctl enable firewalld.service
}

enable_docker_sock_service() {
    systemctl enable var-run-docker.sock.service
}

enable_environment_service() {
    chmod u+x /usr/sbin/export_environment
    systemctl enable stdci-environment.service
}

enable_jenkins_home_service() {
    systemctl enable jenkins-home.service
}

enable_jnlp_slave() {
    systemctl enable jenkins-jnlp-agent.service
}

enable_docker_service() {
    systemctl enable docker
}

main "$@"
