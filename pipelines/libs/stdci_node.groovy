// stdci_node.groovy - A Groovy library for managing STDCI nodes
//
import groovy.json.JsonOutput
import java.security.MessageDigest
import org.jenkinsci.plugins.workflow.cps.CpsThread
import hudson.FilePath

@NonCPS
def get_current_pipeline_node() {
    def thread = CpsThread.current()
    def cv = thread.contextVariables
    def fp
    // The signature of ContextVariableSet.get() changed in later versions of
    // the pipeline plugins. Therefore we first try calling the newer version of
    // the function (that gets 3 arguments), and then the older version.
    try {
        fp = cv.get(FilePath, null, null)
    } catch(MissingMethodException) {
        fp = cv.get(FilePath)
    }
    return fp?.toComputer()?.node
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
