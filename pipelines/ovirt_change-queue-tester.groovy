// ovirt_change-queue-tester - Test pipeline for oVirt change queues
//
def loader_main(loader) {
    def ovirt_release = get_queue_ovirt_release()
    def has_changes
    // Copy methods from loader to this script
    metaClass.checkout_repo = loader.&checkout_repo
    metaClass.checkout_jenkins_repo = loader.&checkout_jenkins_repo

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
            def change_data
            stage('loading changes data') {
                prepare_python_env()
                change_data = load_change_data(ovirt_release)
                if(change_data.summary) {
                    currentBuild.displayName = \
                        "#${currentBuild.id} ${change_data.summary}"
                }
            }
            stage('waiting for artifact builds') {
                wait_for_artifacts(change_data.builds)
            }
            stage('preparing test data') {
                prepare_test_data(change_data)
            }
            stage('running tests') {
                run_tests(ovirt_release)
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
        step([
            $class: 'JUnitResultArchiver',
            testResults: 'exported-artifacts/**/*xml',
            allowEmptyResults: true
        ])
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

def load_change_data(ovirt_release) {
    def mirrors_file_name = 'mirrors.yaml'
    def mirrors_file_path = "exported-artifacts/$mirrors_file_name"
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from __future__ import print_function
            import yaml
            from scripts.change_queue import JenkinsTestedChangeList
            from scripts.mirror_client import (
                mirrors_from_environ, ovirt_tested_as_mirrors
            )

            JenkinsTestedChangeList.setup_logging()
            cl = JenkinsTestedChangeList.load_from_artifact()
            cl.visible_builds.as_json_file()
            print(cl.get_test_summary())
            with open('summary.txt', 'w') as f:
                f.write(cl.get_test_build_title())

            mirrors = mirrors_from_environ('CI_MIRRORS_URL')
            mirrors.update(ovirt_tested_as_mirrors('${ovirt_release}'))
            with open('${mirrors_file_path}', 'w') as mf:
                yaml.safe_dump(mirrors, mf, default_flow_style=False)
        """.stripIndent()
    }
    return [
        builds: readJSON(file: 'builds_list.json'),
        summary: readFile('summary.txt'),
        mirrors_file: mirrors_file_name,
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

def prepare_test_data(change_data) {
    dir('exported-artifacts') {
        def extra_sources = make_extra_sources(change_data.builds)
        writeFile(file: 'extra_sources', text: extra_sources)
        def mirrors = readFile(change_data.mirrors_file)

        print "extra_sources\n-------------\n${extra_sources}"
        print "mirrors\n-------\n${mirrors}"

        stash includes: 'extra_sources', name: 'extra_sources'
        stash includes: change_data.mirrors_file, name: 'mirrors'
    }
}

def run_tests(ovirt_release) {
    run_ost_tests(ovirt_release)
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

@NonCPS
def get_queue_ovirt_release() {
    def match = (env.JOB_NAME =~ /^ovirt-(.*)_change-queue-tester$/)
    if(match.asBoolean()) {
        return match[0][1]
    } else {
        error "Failed to detect oVirt release from job name"
    }
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

def run_ost_tests(ovirt_release) {
    def ost_suit_types = get_available_ost_suit_types(ovirt_release)
    echo "Will run the following OST ($ovirt_release) " +
        "suits: ${ost_suit_types.join(', ')}"
    def branches = [:]
    for(suit_type in ost_suit_types) {
        branches["${suit_type}-suit"] = \
            mk_ost_runner(ovirt_release, suit_type, 'el7')
    }
    parallel branches
}

def get_available_ost_suit_types(ovirt_release) {
    def suit_types_to_use = ["basic"]
    def available_suits = []
    checkout_ost_repo()
    dir('ovirt-system-tests') {
        for(suit_type in suit_types_to_use) {
            if(fileExists("automation/${suit_type}_suite_${ovirt_release}.sh"))
                available_suits << suit_type
        }
    }
    return available_suits
}

def mk_ost_runner(ovirt_release, suit_type, distro) {
    return {
        def suit_dir = "$suit_type-suit-$ovirt_release-$distro"
        // stash an empty file so we don`t get errors in no artifacts get stashed
        writeFile file: '__no_artifacts_stashed__', text: ''
        stash includes: '__no_artifacts_stashed__', name: suit_dir
        try {
            node('integ-tests') {
                run_ost_on_node(ovirt_release, suit_type, distro, suit_dir)
            }
        } finally {
            dir("exported-artifacts/$suit_dir") {
                unstash suit_dir
            }
        }
    }
}

def checkout_ost_repo() {
    checkout_repo('ovirt-system-tests')
}

def run_jjb_script(script_name) {
    def script_path = "jenkins/jobs/confs/shell-scripts/$script_name"
    echo "Running JJB script: ${script_path}"
    def script = readFile(script_path)
    withEnv(["WORKSPACE=${pwd()}"]) {
        sh script
    }
}

def run_ost_on_node(ovirt_release, suit_type, distro, stash_name) {
    checkout_jenkins_repo()
    checkout_ost_repo()
    run_jjb_script('cleanup_slave.sh')
    run_jjb_script('global_setup.sh')
    run_jjb_script('mock_setup.sh')
    try {
        def suit_path = "ovirt-system-tests/$suit_type-suite-$ovirt_release"
        def reposync_config = "*.repo"
        unstash 'mirrors'
        def mirrors = "${pwd()}/mirrors.yaml"
        inject_mirrors(suit_path, reposync_config, mirrors)
        dir(suit_path) {
            stash includes: reposync_config, name: "$stash_name-injected"
        }
        dir('ovirt-system-tests') {
            unstash 'extra_sources'
            mock_runner("${suit_type}_suite_${ovirt_release}.sh", distro, mirrors)
        }
    } finally {
        dir('ovirt-system-tests/exported-artifacts') {
            unstash "$stash_name-injected"
            stash includes: '**', name: stash_name
        }
        run_jjb_script('mock_cleanup.sh')
    }
}

def inject_mirrors(path, file_pattern, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    withEnv(["PYTHONPATH=${pwd()}/jenkins"]) {
        dir(path) {
            sh """\
                #!/usr/bin/env python
                # Try to inject CI mirrors
                from scripts.mirror_client import (
                    inject_yum_mirrors_file_by_pattern,
                    mirrors_from_uri, setupLogging
                )

                setupLogging()
                inject_yum_mirrors_file_by_pattern(
                    mirrors_from_uri('$mirrors'),
                    '$file_pattern'
                )
            """.stripIndent()
        }
    }
}

def mock_runner(script, distro, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    mirrors_arg=''
    if(mirrors != null) {
        mirrors_arg = "--try-mirrors '$mirrors'"
    }
    sh """
        ../jenkins/mock_configs/mock_runner.sh \\
            --execute-script "automation/$script" \\
            --mock-confs-dir ../jenkins/mock_configs \\
            --try-proxy \\
            $mirrors_arg \
            "${distro}.*x86_64"
    """
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
