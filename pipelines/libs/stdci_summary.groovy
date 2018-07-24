// stdci_summary.groovy - Pipeline library to generate STDCI summary.
//

import hudson.model.StringParameterValue
import org.jenkinsci.plugins.workflow.steps.MissingContextVariableException

def default_template

def on_load(loader) {
    // Default template must be loaded here because it's the only place where
    // we have access to 'jenkins/' dir.
    default_template = get_template()
}

def get_template() {
    return readFile("libs/stdci_summary/build_summary.html")
}

@NonCPS
def render_summary(project, threads_summary, summary_template) {
    def artifacts = currentBuild.rawBuild.getArtifacts()

    def findbugs_summary_url = '#'
    def findbugs_summary_url_disabled = 'disabled'
    def findbugs_summary_exists = artifacts.any { it ==~ /find-bugs\/.+\.xml/ }
    if(findbugs_summary_exists) {
        findbugs_summary_url = env.BUILD_URL + '/findbugsResult'
        findbugs_summary_url_disabled = ''
    }

    def junit_summary_url = '#'
    def junit_summary_url_disabled = 'disabled'
    def junit_summary_exists = artifacts.any {
        it ==~ /(.+\.junit\.xml|nosetests.*)/
    }
    if(junit_summary_exists) {
        junit_summary_url = env.BUILD_URL + '/testReport'
        junit_summary_url_disabled = ''
    }

    def data = [
        build_url: env.BUILD_URL,
        blue_ocean_url: env.RUN_DISPLAY_URL,
        change_url: project.change_url,
        change_url_disabled: project.change_url_disabled,
        change_url_title: project.change_url_title,
        rerun_title: project.rerun_title,
        rerun_url: project.rerun_url,
        menu_items: [
            [
                title: 'Test results',
                url: junit_summary_url,
                disabled: junit_summary_url_disabled,
                icon: 'pficon pficon-process-automation'
            ],
            [
                title: 'Test results analyzer',
                url: env.BUILD_URL + '/test_results_analyzer',
                disabled: '',
                icon: 'pficon pficon-cpu'
            ],
            [
                title: 'Findbugs results',
                url: findbugs_summary_url,
                disabled: findbugs_summary_url_disabled,
                icon: 'fa fa-bug'
            ],
            [
                title: 'Full build log',
                url: env.BUILD_URL + '/consoleText',
                disabled: '',
                icon: 'pficon pficon-build'
            ],
        ],
        all_done: !(threads_summary.any { thread, status -> status.result == 'PENDING'}),
        thread_blocks: threads_summary,
    ]

    def engine = new groovy.text.StreamingTemplateEngine()
    return engine.createTemplate(summary_template).make(data).toString()
}

def generate_summary(
    project, threads_summary, summary_template=null, allocate_node=false
) {
    if(!summary_template) {
        summary_template = default_template
    }
    def summary = render_summary(project, threads_summary, summary_template)
    def summary_file = 'ci_build_summary.html'
    try {
        writeFile([file: summary_file, text: summary])
        archiveArtifacts artifacts: summary_file
    } catch(MissingContextVariableException) {
        if(allocate_node) {
            node() {
                writeFile([file: summary_file, text: summary])
                archiveArtifacts artifacts: summary_file
            }
        } else {
            print "STDCI report generation skipped because not on a node"
        }
    }
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
