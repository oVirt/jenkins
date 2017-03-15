// pipeline-loader.groovy - Generic starting point for pipelines. Loads
//                          the actual pipeline code from the 'jenkins' repo
//
node() { wrap([$class: 'TimestamperBuildWrapper']) { ansiColor('xterm') {
    def pipeline
    stage('loading code') {
        dir('jenkins') {
            checkout_jenkins_repo()
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
    pipeline.main()
}}}

def checkout_jenkins_repo() {
    checkout(
        changelog: false, poll: false, scm: [
            $class: 'GitSCM',
            branches: [[name: 'myhead']],
            userRemoteConfigs: [[
            refspec: '+refs/heads/master:myhead',
            url: 'https://gerrit.ovirt.org/jenkins'
            ]]
        ]
    )
}

@NonCPS
def get_pipeline_for_job(name) {
    print("Searching pipeline script for '${name}'")
    def job_to_pipelines = [
        /^numbers_change-queue-tester$/: '$0.groovy',
        /^(.*)_change-queue$/: 'change-queue.groovy',
    ]
    return job_to_pipelines.findResult { key, value ->
        def match = (name =~ key)
        if(match.asBoolean()) {
            return match.replaceAll(value)
        }
    }
}
