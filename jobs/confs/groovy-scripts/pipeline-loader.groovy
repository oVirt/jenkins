// pipeline-loader.groovy - Generic starting point for pipelines. Loads
//                          the actual pipeline code from the 'jenkins' repo
//
def pipeline

node() { wrap([$class: 'TimestamperBuildWrapper']) { ansiColor('xterm') {
    stage('loading code') {
        checkout_jenkins_repo()
        dir('jenkins') {
            def pipeline_file = get_pipeline_for_job(env.JOB_NAME)
            if(pipeline_file == null) {
                error "Could not find a matching pipeline for this job"
            }
            echo "Loading pipeline script: '${pipeline_file}'"
            dir('pipelines') {
                pipeline = load(pipeline_file)
            }
        }
    }
    echo "Launching pipeline script"
    if(pipeline.metaClass.respondsTo(pipeline, 'loader_main')) {
        pipeline.loader_main(this)
    } else {
        pipeline.main()
    }
}}}
if(
    pipeline.metaClass.respondsTo(pipeline, 'loader_main') &&
    pipeline.metaClass.respondsTo(pipeline, 'main')
) {
    pipeline.main()
}

def checkout_jenkins_repo() {
    checkout_repo(
        repo_name: 'jenkins',
        refspec: 'refs/heads/master',
    )
}

def checkout_repo(
    String repo_name,
    String refspec='refs/heads/master',
    String url=null
) {
    if(url == null) {
        url = "https://gerrit.ovirt.org/${repo_name}"
    }
    dir(repo_name) {
        checkout(
            changelog: false, poll: false, scm: [
                $class: 'GitSCM',
                branches: [[name: 'myhead']],
                userRemoteConfigs: [[
                    refspec: "+${refspec}:myhead",
                    url: url
                ]]
            ]
        )
    }
}

def checkout_repo(Map named_args) {
    if('refspec' in named_args) {
        if('url' in named_args) {
            checkout_repo(
                named_args.repo_name, named_args.refspec, named_args.url
            )
        } else {
            checkout_repo(named_args.repo_name, named_args.refspec)
        }
    } else {
        checkout_repo(named_args.repo_name)
    }
}

@NonCPS
def get_pipeline_for_job(name) {
    print("Searching pipeline script for '${name}'")
    def job_to_pipelines = [
        /^standard-enqueue$/: '$0.groovy',
        /^standard-manual-runner$/: 'standard-stage.groovy',
        /^(.*)_standard-(.*)$/: 'standard-stage.groovy',
        /^numbers_change-queue-tester$/: '$0.groovy',
        /^ovirt-(.*)_change-queue-tester$/: 'ovirt_change-queue-tester.groovy',
        /^(.*)_change-queue$/: 'change-queue.groovy',
        /^deploy-to-.*$/: 'deployer.groovy',
    ]
    return job_to_pipelines.findResult { key, value ->
        def match = (name =~ key)
        if(match.asBoolean()) {
            return match.replaceAll(value)
        }
    }
}
