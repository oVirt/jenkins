#!/bin/bash -e
# podlogs.sh - Logs collection for K8s PODs
#
podlogs() {
    oc get "$1" -o go-template='
        {{range .spec.initContainers -}}
            oc logs -c {{.name}} pod/{{$.metadata.name}} > {{.name}}.log &&
            echo {{.name}}.log
        {{end -}}
        {{range .spec.containers -}}
            oc logs -c {{.name}} pod/{{$.metadata.name}} > {{.name}}.log &&
            echo {{.name}}.log
        {{end -}}
        oc describe pod/{{$.metadata.name}} > pod_desc.log &&
        echo pod_desc.log
    ' | bash
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    podlogs "$@"
fi
