#!/bin/bash

readonly LOCKFILE=/var/run/jnlp_daemon.lock
# If you have the PIDFILE, make sure to update jenkins-jnlp-agent.service
readonly PIDFILE=/var/run/jnlp_daemon.pid

daemonize -l "$LOCKFILE" -p "$PIDFILE" \
    java -jar "${JENKINS_AGENT_WORKDIR}/agent.jar" \
    -jnlpUrl "${JENKINS_URL}/computer/${JENKINS_AGENT_NAME}/slave-agent.jnlp" \
    -secret "${JENKINS_SECRET}" \
    -workDir "${JENKINS_AGENT_WORKDIR}"
