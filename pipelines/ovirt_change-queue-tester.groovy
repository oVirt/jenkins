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
        try {
            def change_date
            stage('loading changes date') {
                prepare_python_env()
                change_date = load_change_data()
            }
            stage('waiting for artifact builds') {
                wait_for_artifacts(change_date.builds)
            }
            stage('preparing test date') {
                prepare_test_data(change_date)
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
    } finally {
        archiveArtifacts allowEmptyArchive: true, artifacts: 'exported-artifacts/**'
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

def load_change_data() {
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from scripts.change_queue import JenkinsTestedChangeList

            JenkinsTestedChangeList.setup_logging()
            cl = JenkinsTestedChangeList.load_from_artifact()
            cl.visible_builds.as_json_file()
        """.stripIndent()
    }
    return [
        builds: readJSON(file: 'builds_list.json')
    ]
}

def wait_for_artifacts(builds) {
    waitUntil {
        update_builds_status(builds)
        all_builds_dequeued(builds)
    }
    if(any_builds_removed_from_queue(builds)) {
        error 'Some build jobs were removed from build queue'
    }
    waitUntil { all_builds_done(builds) }
    if(!all_builds_succeeded(builds)) {
        error 'Some build jobs failed'
    }
}

def prepare_test_data(change_date) {
    dir('exported-artifacts') {
        def extra_sources = make_extra_sources(change_date.builds)
        print "extra_sources\n-------------\n${extra_sources}"
        writeFile(file: 'extra_sources', text: extra_sources)
        stash includes: 'extra_sources', name: 'extra_sources'
    }
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

@NonCPS
def update_builds_status(builds) {
    builds.each {
        if(('build_id' in it) || !('queue_id' in it)) {
            return it
        }
        def job = Jenkins.instance.getItem(it.job_name)
        def build = job.builds.find { bld -> bld.queueId == it['queue_id'] }
        if(build == null) {
            if(Jenkins.instance.queue.getItem(it['queue_id']) != null) {
                return it
            }
        } else {
            it.putAll([
                build_id: build.id,
                build_url: build.url
            ])
            print "job: ${it.job_name} build: ${it.build_id} " +
                "(${it.build_url}) moved from queued to running"
        }
        it.remove('queue_id')
        return it
    }
}

@NonCPS
def all_builds_dequeued(builds) {
    return !builds.any {
        if('queue_id' in it) {
            print("${it.job_name} still queued")
            return true
        }
        return false
    }
}

@NonCPS
def any_builds_removed_from_queue(builds) {
    return builds.any {
        if((it.queue_id == null) && (it.build_id == null)) {
            print("${it.job_name} have been manually removed from queue")
            return true
        }
        return false
    }
}

@NonCPS
def all_builds_done(builds) {
    return !builds.any {
        if(Jenkins.instance.getItem(it.job_name).getBuild(it.build_id).isBuilding()) {
            print("${it.job_name} (${it.build_id}) still building")
            return true
        }
        return false
    }
}

@NonCPS
def all_builds_succeeded(builds) {
    return builds.every {
        def build = Jenkins.instance.getItem(it.job_name).getBuild(it.build_id)
        if(build.result.isBetterOrEqualTo(hudson.model.Result.SUCCESS)) {
            return true
        }
        print("${it.job_name} (${it.build_id}) failed building")
        return false
    }
}

@NonCPS
def make_extra_sources(builds) {
    return builds.collect { "${env.JENKINS_URL}${it.build_url}" }.join("\n")
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
