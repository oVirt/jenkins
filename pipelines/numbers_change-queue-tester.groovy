// numbers_change-queue-tester - Test pipeline for the numbers change queue
//
def main() {
    def has_changes
    stage('querying changes to test') {
        has_changes = get_test_changes()
    }
    load_counter_state()
    if(!has_changes) {
        echo "Change queue is empty, exiting"
        currentBuild.displayName = "#${currentBuild.id} [EOQ]"
        save_counter_state()
        return
    }
    try {
        stage('running tests') {
            run_tests()
        }
    } catch(Exception e) {
        stage('reporting results') {
            report_test_results('failure')
        }
        throw(e)
    } finally {
        currentBuild.displayName = get_build_display_name()
        save_counter_state()
    }
    stage('reporting results') {
        report_test_results('success')
    }
}

def get_test_changes() {
    dir('exported-artifacts') { deleteDir() }
    queue_job_name = env.JOB_NAME.replaceFirst('-tester$', '')
    queue_result = build(
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

def prepare_python_env() {
    sh """\
        #!/bin/bash -xe
        if [[ -e '/usr/bin/dnf' ]]; then
            sudo dnf install -y python-jinja2
        else
            sudo yum install -y python-jinja2
        fi
    """.stripIndent()
}

def load_counter_state() {
    echo 'load_counter_state'
    step([
        $class: 'CopyArtifact',
        filter: 'exported-artifacts/counter.dat',
        fingerprintArtifacts: true,
        projectName: env.JOB_NAME,
        selector: [$class: 'StatusBuildSelector', stable: false],
        optional: true,
    ])
}

def save_counter_state() {
    echo 'save_counter_state'
    archive 'exported-artifacts/counter.dat'
}

def run_tests() {
    try {
        withEnv(['PYTHONPATH=jenkins']) {
            run_tests_py()
        }
    } finally {
        echo "Sleeping for a while to allow changes to accumulate in the queue"
        sleep time: 3, unit: 'MINUTES'
    }
}

def run_tests_py() {
    prepare_python_env()
    sh """\
        #!/usr/bin/env python
        from scripts.change_queue import JenkinsTestedChangeList
        from scripts.jenkins_objects import JenkinsObject
        import logging
        from six.moves import range

        JenkinsObject.setup_logging()
        logger = logging.getLogger(__name__)

        def isprime(n):
            '''check if integer n is a prime'''
            # make sure n is a positive integer
            n = abs(int(n))
            # 0 and 1 are not primes
            if n < 2:
                return False
            # 2 is the only even prime number
            if n == 2:
                return True
            # all other even numbers are not primes
            if not n & 1:
                return False
            # range starts with 3 and only needs to go up the squareroot of n
            # for all odd numbers
            for x in range(3, int(n**0.5)+1, 2):
                if n % x == 0:
                    return False
            return True

        cl = JenkinsTestedChangeList.load_from_artifact(fallback_to_new=False)
        logger.info('Testing with key: {0}'.format(cl.test_key))

        with JenkinsObject.persist_in_artifacts('counter.dat') as counter:
            new_sum = getattr(counter, 'sum', 0)
            new_sum += sum(chg.number for chg in cl.change_list)

            if not isprime(new_sum):
                logger.error('Cumulative sum: {0} is not prime'.format(new_sum))
                exit(1)
            counter.sum = new_sum
            logger.info('New cumulative sum: {0}'.format(counter.sum))
    """.stripIndent()
}

@NonCPS
def get_build_display_name() {
    def name_from_log = currentBuild.rawBuild.getLog(50).findResult {
        def match = (it =~ /New cumulative sum: (\d+)/)
        if(match.asBoolean()) {
            return match[0][1]
        }
    }
    if(name_from_log) {
        return "#${currentBuild.id} [sum: ${name_from_log}]"
    }
    return "#${currentBuild.id}"
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

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
