// ovirt_change-queue-tester - Test pipeline for oVirt change queues
//
def main() {
    def has_changes
    stage('querying changes to test') {
        has_changes = get_test_changes()
    }
    if(!has_changes) {
        echo "Change queue is empty, exiting"
        currentBuild.displayName = "#${currentBuild.id} [EOQ]"
        return
    }
    try {
        stage('preparing test date') {
            prepare_python_env()
            // TODO
        }
        stage('running tests') {
            run_tests()
        }
    } catch(Exception e) {
        stage('reporting results') {
            report_test_results('failure')
        }
        throw(e)
    }
    stage('reporting results') {
        report_test_results('success')
    }
    stage('publishing successful artifacts') {
        //TODO
    }
}

def get_test_changes() {
    dir('exported-artifacts') { deleteDir() }
    def queue_job_name = env.JOB_NAME.replaceFirst('-tester$', '')
    def queue_result = build(
        job: queue_job_name,
        parameters: [
            string(name: 'QUEUE_ACTION', value: 'get_next_test'),
            string(name: 'ACTION_ARG', value: 'not-needed'),
        ],
        wait: true,
    )
    step([
        $class: 'CopyArtifact',
        filter: 'exported-artifacts/JenkinsTestedChangeList.dat',
        fingerprintArtifacts: true,
        projectName: queue_job_name,
        selector: [
            $class: 'SpecificBuildSelector',
            buildNumber: "${queue_result.number}",
        ],
        optional: true,
    ])
    return fileExists('exported-artifacts/JenkinsTestedChangeList.dat')
}

def run_tests() {
    echo "Sleeping for a while to allow changes to accumulate in the queue"
    sleep time: 3, unit: 'MINUTES'
}

def report_test_results(result) {
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from scripts.change_queue import JenkinsTestedChangeList

            JenkinsTestedChangeList.setup_logging()
            cl = JenkinsTestedChangeList.load_from_artifact()
            cl.on_test_${result}().as_pipeline_build_step_json()
        """.stripIndent()
    }
    build_args = readJSON(file: 'build_args.json')
    build_args['wait'] = true
    build build_args
}

def prepare_python_env() {
    sh """\
        #!/bin/bash -xe
        if [[ -e '/usr/bin/dnf' ]]; then
            sudo dnf install -y python-jinja2 python-paramiko
        else
            sudo yum install -y python-jinja2 python-paramiko
        fi
    """.stripIndent()
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
