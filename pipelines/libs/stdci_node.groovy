// stdci_node.groovy - A Groovy library for managing STDCI nodes
//
import groovy.json.JsonOutput
import java.security.MessageDigest
import org.jenkinsci.plugins.workflow.cps.CpsThread
import hudson.FilePath

@NonCPS
def get_current_pipeline_node() {
    def thread = CpsThread.current()
    return thread.contextVariables.get(FilePath)?.toComputer()?.node
}


def get_current_pipeline_node_details() {
    def node = get_current_pipeline_node()
    return [
        'name': node.nodeName,
        'labels': node.labelString,
    ]
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
