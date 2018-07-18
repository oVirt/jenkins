#!/bin/bash -ex

main(){
    enable_docker_sock_service
    enable_environment_service
    enable_jenkins_home_service
    enable_jnlp_slave
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

main "$@"
