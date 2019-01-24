// pipeline-loader.groovy - Generic starting point for pipelines. Loads
//                          the actual pipeline code from the 'jenkins' repo
//
def pipeline

timestamps { ansiColor('xterm') {
    node(env?.LOADER_NODE_LABEL) {
        stage('loading code') {
            dir("exported-artifacts") { deleteDir() }
            checkout_jenkins_repo()
            dir('jenkins') {
                def pipeline_file = get_pipeline_for_job(env.JOB_NAME)
                if(pipeline_file == null) {
                    error "Could not find a matching pipeline for this job"
                }
                echo "Loading pipeline script: '${pipeline_file}'"
                dir('pipelines') {
                    pipeline = load_code(pipeline_file)
                }
            }
        }
        echo "Launching pipeline script"
        if(pipeline.metaClass.respondsTo(pipeline, 'loader_main')) {
            pipeline.loader_main(this)
        } else {
            pipeline.main()
        }
    }
    if(
        pipeline.metaClass.respondsTo(pipeline, 'loader_main') &&
        pipeline.metaClass.respondsTo(pipeline, 'main')
    ) {
        pipeline.main()
    }
}}

def load_code(String code_file, def load_as=null) {
    def code = load(code_file)
    if(code.metaClass.respondsTo(code, 'on_load')) {
        code.on_load(load_as ?: this)
    }
    return code
}

def checkout_jenkins_repo() {
    def url_prefix = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
    checkout_repo(
        repo_name: 'jenkins',
        refspec: env.STDCI_SCM_REFSPEC ?: 'refs/heads/master',
        url: env.STDCI_SCM_URL ?: "${url_prefix}/jenkins"
    )
}

def checkout_repo(
    String repo_name,
    String refspec='refs/heads/master',
    String url=null,
    String head=null,
    String clone_dir_name=null
) {
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
        checkout(
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
                    [$class: 'UserIdentity',
                        email: env.GIT_AUTHOR_NAME,
                        name: env.GIT_AUTHOR_EMAIL
                    ],
                ],
            ]
        )
        sh """
            WORKSPACE="\${WORKSPACE:-\$(dirname \$PWD)}"

            usrc="\$WORKSPACE/jenkins/scripts/usrc.py"
            [[ -x "\$usrc" ]] || usrc="\$WORKSPACE/jenkins/scripts/usrc_local.py"

            "\$usrc" --log -d get
        """
    }
}

def checkout_repo(Map named_args) {
    if('refspec' in named_args) {
        checkout_repo(
            named_args.repo_name, named_args.refspec,
            named_args.url, named_args.head
        )
    } else {
        checkout_repo(named_args.repo_name)
    }
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
    ]
    return job_to_pipelines.findResult { key, value ->
        def match = (name =~ key)
        if(match.asBoolean()) {
            return match.replaceAll(value)
        }
    }
}
