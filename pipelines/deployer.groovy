// deployer.groovy - Jenkins pipeline script for deploying packages to
//                   repos hosted on OpenShift
//
def on_load(loader) {
    // Copy methods from loader to this script
    metaClass.checkout_repo = {
        repo_name, refspec='refs/heads/master', url=null, head=null,
        clone_dir_name=null -> loader.metaClass.invokeMethod(
            loader, 'checkout_repo',
            [repo_name, refspec, url, head, clone_dir_name])
    }
    metaClass.checkout_jenkins_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_jenkins_repo', args)
    }
    metaClass.run_jjb_script = { ...args ->
        loader.metaClass.invokeMethod(loader, 'run_jjb_script', args)
    }

    metaClass.load_code = { code_file, load_as=null ->
        loader.metaClass.invokeMethod(
            loader, 'load_code', [code_file, load_as])
    }
    hook_caller = loader.load_code('libs/stdci_hook_caller.groovy', this)
    project_lib = load_code('libs/stdci_project.groovy', this)
    stdci_runner_lib = load_code('libs/stdci_runner.groovy', this)
}

def loader_main(loader) {
    // We need to define this function even if it does nothing so that
    // pipeline-loader.groovy releases the loader node before calling main()
}

def main() {
    def repoman_sources

    try {
        stage('find builds to deploy') {
            repoman_sources = env.REPOMAN_SOURCES ?: get_sources_from_triggers()
            if(!repoman_sources) {
                error('No repoman sources passed, will not run deployment')
            }
            def sources_out
            sources_out =  "will deploy build from the following sources:\n"
            sources_out += "---------------------------------------------\n"
            sources_out += repoman_sources
            print(sources_out)
        }
        stage("Deploying to '${env.REPO_NAME}' repo") {
            deploy_to(env.REPO_NAME, repoman_sources)
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

def deploy_to(repo_name, repoman_sources) {
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
    withEnv(["REPOMAN_SOURCES=$repoman_sources"]) {
        stdci_runner_lib.run_std_ci_jobs(
            project: project,
            jobs: jobs,
        )
    }
}

def email_notify(status, recipients='infra@ovirt.org') {
    emailext(
        subject: "[oVirt Jenkins] ${env.JOB_NAME}" +
            " - Build #${env.BUILD_NUMBER} - ${status}!",
        body: [
            "Build: ${env.BUILD_URL}",
            "Build Name: ${currentBuild.displayName}",
            "Build Status: ${status}",
            "Gerrit change: ${params.GERRIT_CHANGE_URL}",
            "- title: ${params.GERRIT_CHANGE_SUBJECT}",
            "- project: ${params.GERRIT_PROJECT}",
            "- branch: ${params.GERRIT_BRANCH}",
            "- author: ${params.GERRIT_CHANGE_OWNER_NAME}" +
            " <${params.GERRIT_CHANGE_OWNER_EMAIL}>",
        ].join("\n"),
        to: recipients,
        mimeType: 'text/plain'
    )
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
