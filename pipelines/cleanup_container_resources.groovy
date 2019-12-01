// cleanup_container_resources.groovy - Jenkins pipeline script for cleaning container
//                   resources from repos hosted on OpenShift
//
import groovy.transform.Field

def on_load(loader) {
    project_lib = loader.load_code('libs/stdci_project.groovy')
    stdci_runner_lib = loader.load_code('libs/stdci_runner.groovy')
    def email_notify_lib = loader.load_code('libs/email_notify.groovy')
    email_notify = email_notify_lib.&email_notify
}

def loader_main(loader) {
    // We need to define this function even if it does nothing so that
    // pipeline-loader.groovy releases the loader node before calling main()
}

def main() {
    try {
        stage("Cleaning resources from '${env.REPO_NAME}' repo") {
            cleanup_resources(env.REPO_NAME)
        }
    } catch(Exception e) {
        email_notify('FAILURE')
        throw(e)
    }
}

def cleanup_resources(repo_name) {
    def url_prefix = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
    def project = project_lib.new_project(
        name: 'jenkins',
        refspec: env.STDCI_SCM_REFSPEC ?: 'refs/heads/master',
        clone_url: env.STDCI_SCM_URL ?: "${url_prefix}/jenkins"
    )
    def jobs = [[
        'stage': "run-cleanup-playbook",
        'substage': 'default',
        'distro': 'el7',
        'arch': 'x86_64',
        'script': 'automation/run-cleanup-playbook.sh',
        'runtime_reqs': [:],
        'release_branches': [:],
        'reporting': ['style': 'stdci'],
        'timeout': '3h'
    ]]
    stdci_runner_lib.run_std_ci_jobs(
        project: project,
        jobs: jobs,
    )
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this