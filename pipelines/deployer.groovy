// deployer.groovy - Jenkins pipeline script for deploying packages to
//                   repos hosted on OpenShift
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
    def repoman_sources
    def flatten_layers=false

    try {
        stage('find builds to deploy') {
            flatten_layers = should_flatten_layers()
            repoman_sources = env.REPOMAN_SOURCES ?: get_sources_from_triggers()
            if(!repoman_sources) {
                if(flatten_layers) {
                    repoman_sources = '# empty build to flatten image layers\n'
                } else {
                    print('No repoman sources passed, will not run deployment')
                    return
                }
            }
            def sources_out
            sources_out =  'will deploy build from the following sources:\n'
            sources_out += '---------------------------------------------\n'
            sources_out += repoman_sources
            if(flatten_layers) {
                sources_out += '---------------------------------------------\n'
                sources_out += 'Would fatten container image layers'
            }
            print(sources_out)
        }
        if(repoman_sources) {
            stage("Deploying to '${env.REPO_NAME}' repo") {
                deploy_to(env.REPO_NAME, repoman_sources, flatten_layers)
            }
        }
    } catch(Exception e) {
        email_notify('FAILURE')
        throw(e)
    }
}

@NonCPS
def get_sources_from_triggers() {
    return currentBuild.getBuildCauses().findAll({ cause ->
        'upstreamProject' in cause
    }).collect({ cause ->
         "jenkins:${env.JENKINS_URL}${cause.upstreamUrl}${cause.upstreamBuild}\n"
    }).join()
}

@NonCPS
def should_flatten_layers() {
    return is_time_triggered(currentBuild) && (
        currentBuild.previousBuild.is(null)
        || !is_time_triggered(currentBuild.previousBuild)
    )
}

@NonCPS
def is_time_triggered(build) {
    return build.getBuildCauses().any({ cause ->
        cause._class == 'hudson.triggers.TimerTrigger$TimerTriggerCause'
    })
}

def deploy_to(repo_name, repoman_sources, flatten_layers) {
    def url_prefix = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
    def project = project_lib.new_project(
        name: 'jenkins',
        refspec: env.STDCI_SCM_REFSPEC ?: 'refs/heads/master',
        clone_url: env.STDCI_SCM_URL ?: "${url_prefix}/jenkins"
    )
    def jobs = [[
        'stage': "run-deploy-playbook",
        'substage': 'default',
        'distro': 'el7',
        'arch': 'x86_64',
        'script': 'automation/run-deploy-playbook.sh',
        'runtime_reqs': [:],
        'release_branches': [:],
        'reporting': ['style': 'stdci'],
        'timeout': '3h'
    ]]
    withEnv([
        "REPOMAN_SOURCES=$repoman_sources",
        "FLATTEN_LAYERS=${flatten_layers as String}",
    ]) {
        stdci_runner_lib.run_std_ci_jobs(
            project: project,
            jobs: jobs,
        )
    }
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
