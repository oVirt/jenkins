// change-queue-tester - Test pipeline for change queues
//
def test_functions

def on_load(loader) {
    // Copy methods from loader to this script
    metaClass.checkout_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_repo', args)
    }
    metaClass.checkout_jenkins_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_jenkins_repo', args)
    }
    metaClass.run_jjb_script = { ...args ->
        loader.metaClass.invokeMethod(loader, 'run_jjb_script', args)
    }

    // Every change queue tester job is supposed to have another *.groovy file
    // that contains the actual testing functions
    def tf_file = env.JOB_NAME.replaceFirst(
        '^(.*?)(-[^-]*)?(_change-queue-tester)$', '$1$3.groovy'
    )
    print "Loading change queue test functions from: $tf_file"
    test_functions = loader.load_code(tf_file, this)
}

def loader_main(loader) {
    def has_changes
    def change_data

    try {
        stage('loading changes data') {
            has_changes = get_test_changes()
            if(!has_changes) {
                echo "Change queue is empty, exiting"
                currentBuild.displayName = "#${currentBuild.id} [EOQ]"
                currentBuild.description = 'No changes to test'
                return
            }
            change_data = load_change_data()
            if(change_data.summary) {
                currentBuild.displayName = \
                    "#${currentBuild.id} ${change_data.title}"
                currentBuild.description = change_data.summary
            }
        }
        if(!has_changes) {
            // This is needed because the return above only exists the stage
            // and not this whole function
            return
        }
        try {
            stage('waiting for artifact builds') {
                change_data.builds = wait_for_artifacts(change_data.builds)
            }
            stage('preparing test data') {
                prepare_test_data(change_data)
            }
            stage('running tests') {
                run_tests(change_data)
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
        deploy(change_data)
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
    def mirrors_file_name = 'mirrors.yaml'
    def mirrors_file_path = "exported-artifacts/$mirrors_file_name"
    def extra_py = ''

    if(test_functions.metaClass.respondsTo(
        test_functions, 'extra_load_change_data_py'
    )) {
        extra_py = test_functions.extra_load_change_data_py('cl', 'mirrors')
    }
    withEnv(['PYTHONPATH=jenkins']) {
        // Note: We cannot simply use string interpolation to embed extra_py
        // below because it is probably indented differently then the code we
        // have here
        sh """\
            #!/usr/bin/env python
            from __future__ import print_function
            import yaml
            from scripts.change_queue import JenkinsTestedChangeList
            from scripts.mirror_client import mirrors_from_environ

            JenkinsTestedChangeList.setup_logging()
            cl = JenkinsTestedChangeList.load_from_artifact()

            mirrors = mirrors_from_environ('CI_MIRRORS_URL')
        """.stripIndent() +
        extra_py.stripIndent() +
        """
            cl.visible_builds.as_json_file()
            print(cl.get_test_summary())
            with open('summary.txt', 'w') as f:
                f.write(next(iter(cl.get_test_summary().splitlines()), ''))
            with open('title.txt', 'w') as f:
                f.write(cl.get_test_build_title())

            with open('${mirrors_file_path}', 'w') as mf:
                yaml.safe_dump(mirrors, mf, default_flow_style=False)
        """.stripIndent()
    }
    return [
        builds: readJSON(file: 'builds_list.json'),
        summary: readFile('summary.txt'),
        title: readFile('title.txt'),
        mirrors_file: mirrors_file_name,
    ]
}

def wait_for_artifacts(builds) {
    waitUntil {
        builds = update_builds_status(builds)
        all_builds_dequeued(builds)
    }
    if(any_builds_removed_from_queue(builds)) {
        error 'Some build jobs were removed from build queue'
    }
    waitUntil {
        builds = update_builds_status(builds)
        all_builds_done(builds)
    }
    if(!all_builds_succeeded(builds)) {
        error 'Some build jobs failed'
    }
    return builds
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

def run_tests(change_data) {
    if(test_functions.metaClass.respondsTo(test_functions, 'run_tests')) {
        test_functions.run_tests(change_data)
    } else {
        echo "No tests defined for this change-queue"
    }
}

def deploy(change_data) {
    if(test_functions.metaClass.respondsTo(test_functions, 'deploy')) {
        test_functions.deploy(change_data)
    } else {
        echo "No deployment method defined for this change-queue"
    }
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
def update_builds_status(builds) {
    builds.findResults {
        def job = Jenkins.instance.getItem(it.job_name)
        if(job == null) {
            print("Job: ${it.job_name} seems to have been removed - ignoring")
            // returning null will make this build record not appear in the
            // returned collection
            return null
        }
        if(('build_id' in it) || !('queue_id' in it)) {
            return it
        }
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
        def job = Jenkins.instance.getItem(it.job_name)
        if(job == null) {
            print("Job: ${it.job_name} seems to have been removed - ignoring")
            return false
        }
        def build = job.getBuild(it.build_id)
        if(build == null) {
            print("Cannot find build ${it.build_id} of ${it.job_name}.")
            return false
        }
        if(build.isBuilding()) {
            print("${it.job_name} (${it.build_id}) still building")
            return true
        }
        return false
    }
}

@NonCPS
def all_builds_succeeded(builds) {
    return builds.every {
        def job = Jenkins.instance.getItem(it.job_name)
        if(job == null) {
            print("Job: ${it.job_name} seems to have been removed - ignoring")
            return true
        }
        def build = job.getBuild(it.build_id)
        if(build == null) {
            print("Cannot find build ${it.build_id} of ${it.job_name}.")
            return false
        }
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
