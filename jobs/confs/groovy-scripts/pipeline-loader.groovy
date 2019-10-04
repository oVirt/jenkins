// pipeline-loader.groovy - Generic starting point for pipelines. Loads
//                          the actual pipeline code from the 'jenkins' repo
//
import groovy.transform.Field

def pipeline

if(env.RUNNING_IN_LOADER?.toBoolean()) {
    // This code runs if this file was loaded as pipeline
    return this
} else {
    // This code runs if this file was embedded directly as the script of a
    // pipeline job, it is the only part of this file that cannot be reloaded
    // dynamically
    timestamps { main() }
}

def loader_main(loader) {
    // Since this script can also be used as a pipeline, we need to define this
    // function so that the main() function runs outside of the loader node and
    // can allocate its own loader node
}

def main() {
    node(env?.LOADER_NODE_LABEL) {
        stage('loading code') {
            dir("exported-artifacts") { deleteDir() }
            def checkoutData = checkout_jenkins_repo()
            if(checkoutData.CODE_FROM_EVENT) {
                echo "Code loaded from STDCI repo event"
            }
            if (!env?.LOADER_NODE_LABEL?.endsWith('-container')) {
                run_jjb_script('cleanup_slave.sh')
                run_jjb_script('global_setup.sh')
            }
            dir('jenkins') {
                def pipeline_file
                if(
                    checkoutData.CODE_FROM_EVENT
                    && !(env.RUNNING_IN_LOADER?.toBoolean())
                    && loader_was_modified()
                ) {
                    echo "Going to reload the pipeline loader"
                    pipeline_file = 'pipeline-loader.groovy'
                } else {
                    pipeline_file = get_pipeline_for_job(env.JOB_NAME)
                }
                if(pipeline_file == null) {
                    error "Could not find a matching pipeline for this job"
                }
                echo "Loading pipeline script: '${pipeline_file}'"
                dir('pipelines') {
                    withEnv(['RUNNING_IN_LOADER=true']) {
                        pipeline = load_code(pipeline_file)
                    }
                }
            }
        }
        echo "Launching pipeline script"
        if(pipeline.metaClass.respondsTo(pipeline, 'loader_main')) {
            withEnv(['RUNNING_IN_LOADER=true']) {
                pipeline.loader_main(this)
            }
        } else {
            withEnv(['RUNNING_IN_LOADER=true']) {
                pipeline.main()
            }
        }
        if (!env?.LOADER_NODE_LABEL?.endsWith('-container')) {
            run_jjb_script('global_setup_apply.sh')
        }
    }
    if(
        pipeline.metaClass.respondsTo(pipeline, 'loader_main') &&
        pipeline.metaClass.respondsTo(pipeline, 'main')
    ) {
        withEnv(['RUNNING_IN_LOADER=true']) {
            pipeline.main()
        }
    }
}

@Field def loaded_code = [:]

def load_code(String code_file) {
    if(!(code_file in loaded_code)) {
        def code = load(code_file)
        if(code.metaClass.respondsTo(code, 'on_load')) {
            code.on_load(this)
        }
        loaded_code[code_file] = code
    }
    return loaded_code[code_file]
}

def checkout_jenkins_repo() {
    String url_prefix = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
    String configured_url = env.STDCI_SCM_URL ?: "${url_prefix}/jenkins"
    String event_url = "https://${env.GERRIT_NAME}/${env.GERRIT_PROJECT}"
    String refspec = env.STDCI_SCM_REFSPEC ?: 'refs/heads/master'
    def code_from_event = false
    if(configured_url == event_url) {
        refspec = env.GERRIT_REFSPEC
        code_from_event = true
    }
    def checkoutData = checkout_repo(
        repo_name: 'jenkins',
        refspec: refspec,
        url: configured_url,
    )
    checkoutData.CODE_FROM_EVENT = code_from_event
    return checkoutData
}

def checkout_repo(
    String repo_name,
    String refspec='refs/heads/master',
    String url=null,
    String head=null,
    String clone_dir_name=null
) {
    def checkoutData
    if(url == null) {
        url_prefix = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
        url = "${url_prefix}/${repo_name}"
    }
    if(head == null) {
        head = 'myhead'
    }
    if(clone_dir_name == null) {
        clone_dir_name = repo_name
    }
    dir(clone_dir_name) {
        checkoutData = checkout(
            changelog: false, poll: false, scm: [
                $class: 'GitSCM',
                branches: [[name: head]],
                userRemoteConfigs: [[
                    refspec: "+${refspec}:myhead",
                    url: url
                ]],
                extensions: [
                    [$class: 'CleanBeforeCheckout'],
                    [$class: 'PerBuildTag'],
                    [$class: 'CloneOption', timeout: 20],
                    [$class: 'UserIdentity',
                        email: env.GIT_AUTHOR_NAME,
                        name: env.GIT_AUTHOR_EMAIL
                    ],
                ],
            ]
        )
        sshagent(['std-ci-git-push-credentials']) {
            sh """
                WORKSPACE="\${WORKSPACE:-\$(dirname \$PWD)}"

                usrc="\$WORKSPACE/jenkins/scripts/usrc.py"
                [[ -x "\$usrc" ]] || usrc="\$WORKSPACE/jenkins/scripts/usrc_local.py"

                "\$usrc" --log -d get
            """
        }
    }
    return checkoutData
}

def checkout_repo(Map named_args) {
    if('refspec' in named_args) {
        return checkout_repo(
            named_args.repo_name, named_args.refspec,
            named_args.url, named_args.head
        )
    } else {
        return checkout_repo(named_args.repo_name)
    }
}

def loader_was_modified() {
    def result = sh(
        label: 'pipeline-loader diff check',
        returnStatus: true,
        script: '''\
            usrc="$WORKSPACE/jenkins/scripts/usrc.py"
            [[ -x "$usrc" ]] || usrc="$WORKSPACE/jenkins/scripts/usrc_local.py"

            "$usrc" --log -d changed-files | grep 'pipeline-loader.groovy$'
        '''
    )
    return (result == 0)
}

def run_jjb_script(script_name) {
    def script_path = "jenkins/jobs/confs/shell-scripts/$script_name"
    echo "Running JJB script: ${script_path}"
    def script = readFile(script_path)
    withEnv(["WORKSPACE=${pwd()}"]) {
        sh script
    }
}

@NonCPS
def get_pipeline_for_job(name) {
    print("Searching pipeline script for '${name}'")
    def job_to_pipelines = [
        /^standard-enqueue$/: '$0.groovy',
        /^standard-manual-runner$/: 'standard-stage.groovy',
        /^(.*)_standard-(.*)$/: 'standard-stage.groovy',
        /^(.*)_change-queue(-tester)?$/: 'change-queue$2.groovy',
        /^deploy-to-.*$/: 'deployer.groovy',
        /^(.*)_gate$/: 'gate.groovy'
    ]
    return job_to_pipelines.findResult { key, value ->
        def match = (name =~ key)
        if(match.asBoolean()) {
            return match.replaceAll(value)
        }
    }
}
