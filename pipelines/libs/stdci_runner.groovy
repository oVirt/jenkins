// stdci_runner.groovy - Pipeline wrapper for mock_runner
//
import org.jenkinsci.plugins.workflow.cps.CpsScript
import groovy.transform.Field

@Field def run_jjb_script
@Field def checkout_jenkins_repo
@Field def loader_node
@Field def withHook
@Field def node

class TestFailedRef implements Serializable {
    // Flag used to indicate that the actual test failed and not something else
    // Its inside a class so we can pass it by reference by passing object
    // instance around
    Boolean test_failed = false
}

def on_load(loader) {
    project_lib = loader.load_code('libs/stdci_project.groovy')
    stdci_summary_lib = loader.load_code('libs/stdci_summary.groovy')
    node_lib = loader.load_code('libs/stdci_node.groovy')
    def hook_caller = loader.load_code('libs/stdci_hook_caller.groovy')

    run_jjb_script = loader.&run_jjb_script
    checkout_jenkins_repo = loader.&checkout_jenkins_repo
    loader_node = loader.&loader_node
    withHook = hook_caller.&withHook
}

def run_std_ci_jobs(Map named_args) {
    run_std_ci_jobs(
        named_args.project,
        named_args.jobs,
        named_args.get('mirrors', null),
        named_args.get('extra_sources', null)
    )
}

def run_std_ci_jobs_with_loader(Map named_args) {
    // A version of run_std_ci_jobs that allocates a loader node to run with if
    // its needed, only named args are supported
    if(named_args?.jobs?.podspecs.any()) {
        // If we need to run PODs, allocate a node to manage them
        loader_node(enable_nfs: true) {
            checkout_jenkins_repo()
            stdci_runner_lib.run_std_ci_jobs(named_args)
        }
    } else {
        stdci_runner_lib.run_std_ci_jobs(named_args)
    }
}

def run_std_ci_jobs(project, jobs, mirrors=null, extra_sources=null) {
    def branches = [:]
    def report = new PipelineReporter(this, project)
    remove_blacklisted_jobs(jobs)
    if(jobs) {
        for(job in jobs) {
            branches[get_job_name(job)] = mk_std_ci_runner(
                report.mk_thread_reporter(job), project, job,
                mirrors, job?.extra_sources ?: extra_sources
            )
        }
        parallel branches
    } else {
        loader_node() {
            report.no_jobs()
        }
    }
}

def mk_std_ci_runner(report, project, job, mirrors=null, extra_sources=null) {
    if(job.podspecs) {
        return mk_openshift_std_ci_runner(report, project, job, mirrors, extra_sources)
    } else {
        return mk_mock_std_ci_runner(report, project, job, mirrors, extra_sources)
    }
}

def mk_mock_std_ci_runner(report, project, job, mirrors=null, extra_sources=null) {
    return {
        report.status('PENDING', 'Allocating runner node')
        String node_label = get_std_ci_node_label(project, job)
        if(node_label.empty) {
            print "This script has no special node requirements"
        } else {
            print "This script required nodes with label: $node_label"
        }
        node(node_label) {
            run_std_ci_on_node(report, project, job, mirrors, extra_sources)
        }
    }
}

def mk_openshift_std_ci_runner(report, project, job, mirrors=null, extra_sources=null) {
    return {
        run_std_ci_in_pods(report, project, job, mirrors, extra_sources)
    }
}

def wait_pod_phase(pod, wait_on_phases, label) {
    return sh(
        label: label,
        returnStdout: true,
        script: """#!/bin/bash
            tout=2
            while :; do
                coproc \
                    timeout \$tout \
                    oc get -w '$pod' -o go-template=\$'{{.status.phase}}\\n'
                read phase <&"\${COPROC[0]}"
                echo "Current phase: \$phase" 1>&2
                case "\$phase" in
                        ${wait_on_phases.join('|')})
                            echo "Waiting (up to \$tout secs)" 1>&2 ;;
                        *)
                            kill -INT \$COPROC_PID; echo "\$phase"; exit;;
                esac
                wait \$COPROC_PID
                if [[ \$tout -lt 10 ]]; then
                    tout=\$((tout * 2))
                fi
            done
        """,
    ).trim()
}

def run_std_ci_in_pods(report, project, job, mirrors=null, extra_sources=null) {
    Boolean success = false
    Boolean test_failed = false
    String job_dir = get_job_dir(job)
    sh(
        label: 'Creating results directory',
        script: "umask 0007; mkdir -p /exported-artifacts/$job_dir"
    )
    if(extra_sources && job.decorate) {
        writeFile file: "/exported-artifacts/$job_dir/extra_sources", \
            text: extra_sources
        println "extra_sources file was created"
    }
    if(mirrors && job.decorate) {
        writeFile file: "/exported-artifacts/$job_dir/mirrors.yaml", \
            text: mirrors
        println "mirrors.yaml file was created"
    }
    job.podspecs.each { podspec ->
        report.status('PENDING', 'Allocating POD')
        def pod = sh(
            label: 'Create POD',
            returnStdout: true,
            script: """#!/bin/bash
                echo "Creating POD with the following configuration" 1>&2
                echo "=============================================" 1>&2
                cat <<'EOPOD' |\n$podspec\nEOPOD
                ${pod_nfs_patch(job)} |
                tee /dev/stderr |
                oc create -o name -f -
            """
        ).trim()
        echo "Running in POD: $pod"
        try {
            timeout(time: env.STDCI_POD_START_TIMEOUT ?: 3600, unit: 'SECONDS') {
                wait_pod_phase(pod, ['Pending'], "Waiting for POD to start")
            }
            report.status('PENDING', 'Running test')
            sh(label: "Running POD", script: "oc logs -f '$pod'")
            // Wait until the pod finishes, we do not enforce a timeout here,
            // because the STDCI DSL should already inject timeout configuration
            // into the POD itself
            def phase = wait_pod_phase(
                pod, ['Pending', 'Running'], "Waiting for POD to terminate"
            )
            if(phase == 'Succeeded') {
                success = true
            } else {
                if(phase == 'Failed') {
                    test_failed = true
                }
                error "Pod: '${pod}' failed"
            }
        } finally {
            report.status('PENDING', 'Collecting results')
            dir('/exported-artifacts') {
                dir("$job_dir/pod_logs") { sh(
                    label: "Collect POD logs",
                    script: "$env.WORKSPACE/jenkins/scripts/podlogs.sh '$pod'"
                ) }
                archiveArtifacts allowEmptyArchive: true, \
                    artifacts: "$job_dir/**"
                junit keepLongStdio: true, allowEmptyResults: true, \
                    testResults: "$job_dir/**/*xml"
            }
            // We user returnStatus here to avoid throwing an exception if the
            // POD is not there or we fail from other reason
            sh(
                label: 'Remove POD',
                returnStatus: true,
                script: "oc delete '$pod'"
            )
            if(success) {
                report.status('SUCCESS', 'Test is successful')
            } else if (test_failed) {
                report.status('FAILURE', 'Test script failed')
            } else {
                report.status('ERROR', 'Testing system error')
            }
        }
    }
}

def pod_nfs_patch(job) {
    // We patch-in the NFS server address in case we changed the
    // loader node since the YAML was generated
    //
    if((!job.decorate) || (!env.EXPORTED_ARTIFACTS_HOST)) {
        return 'cat'
    }
    return [
        "oc patch --local -f - -o yaml -p '{",
            '"spec": {"volumes": [{',
                '"name": "exported-artifacts",',
                '"nfs": {',
                    '"server": "' + env.EXPORTED_ARTIFACTS_HOST +'",',
                    '"path": "/exported-artifacts/' + get_job_dir(job) +'"',
                '}',
            '}]}',
        "}'",
    ].join()
}

def get_job_dir(job) {
    return get_job_name(job)
}

def get_node_label_for_project(project) {
    switch(project.name) {
        case ~/^lago(-.+)?$/:
            return 'lago_templates'
        case ~/^(stage-.+|.+-staging_standard-.+)/:
            // Staging projects for testing only
            return 'staging_label'
        case ~/^ost-images/:
            // This is for ost images
            return 'templates'
        default:
            // We couldn't find a specific node label for $project
            return null
    }
}

@NonCPS
def get_std_ci_node_label(project, job) {
    def label_conditions = []
    def project_specific_node = job.runtime_reqs?.projectspecificnode
    // readYaml method converts the string 'true'/'false' into Booleans.
    // We need to ensure we enter the condition only if the input was indeed
    // 'true' and not just any random String.
    if(project_specific_node in Boolean && project_specific_node) {
        def label = get_node_label_for_project(project)
        if(label) {
            label_conditions << label
        }
    }
    if(
        job.runtime_reqs?.supportnestinglevel >= 2 &&
        job.runtime_reqs?.isolationlevel == 'container'
    ) {
        if (project?.org == 'kubevirt') {
            // check true explicitly to avoid true-ish conditions
            if(job.runtime_reqs?.sriovnic == true) {
                label_conditions << 'integ-tests-container_sriov-nic'
            } else {
                label_conditions << 'integ-tests-container_fast'
            }
        } else {
            label_conditions << 'integ-tests-container'
        }
    } else if(
        job.runtime_reqs?.supportnestinglevel >= 2 ||
        job.runtime_reqs?.isolationlevel == 'physical'
    ) {
        label_conditions << 'integ-tests'
    }
    if(job.runtime_reqs?.supportnestinglevel == 1) {
        label_conditions << 'nested'
    }
    if(job.runtime_reqs?.hostdistro =~ /^(?i)same$/) {
        label_conditions << job.distro
    } else if(job.runtime_reqs?.hostdistro =~ /^(?i)newer$/) {
        label_conditions << get_newer_distros_label(job.distro)
    } else if(!job.runtime_reqs?.hostdistro.equals('any')) {
        label_conditions << job.runtime_reqs?.hostdistro
    }
    // Only run FCRAW jobs on FC >= 29 slaves
    if(job.distro == 'fcraw') {
        label_conditions << get_newer_distros_label('el8')
    }
    if (job.arch != "x86_64") {
        label_conditions << job.arch
    }
    if(env.RUNNING_IN_PSI?.toBoolean()) {
        label_conditions << job.distro
        label_conditions << 'psi'
        if(job.runtime_reqs?.supportnestinglevel <= 1) {
            label_conditions << 'virtual'
        }
        if(job.beaker_label) {
            label_conditions << job.beaker_label
        }
    }
    label_conditions.unique()
    return label_conditions.join(' && ')
}

@NonCPS
def get_newer_distros_label(distro) {
    String[] host_distros = [
        'el7', 'rhel7', 'el8stream', 'el8', 'rhel8', 'fc32', 'el9stream'
    ]
    int dist_idx = host_distros.findIndexOf { it == distro }
    if(dist_idx < 0) {
        throw new Exception("Can't find newer distros for ${job.distro}")
    }
    String[] job_distros = host_distros[dist_idx..<host_distros.size()]
    if(env.RUNNING_IN_PSI?.toBoolean()) {
        return distro
    }
    return "(${job_distros.join(' || ')})"
}

def run_std_ci_on_node(report, project, job, mirrors=null, extra_sources=null) {
    TestFailedRef tfr = new TestFailedRef()
    Boolean success = false
    try {
        try {
            node = node_lib.get_current_pipeline_node_details()
            print("Running on node: $node.name ($node.labels)")
            if(job.runtime_reqs?.isolationlevel == 'container') {
                sh """
                    echo \"OpenShift node name: \${_CI_ENV_NODE_NAME:-NO DATA}\"
                """
            }
            report.status('PENDING', 'Setting up test environment')
            // Clear al left-over artifacts from previous builds
            dir(get_job_dir(job)) { deleteDir() }
            checkout_jenkins_repo()
            // The OST check is because currently we need to reprovision the server with mock until
            // we will have beaker.
            if (!env.RUNNING_IN_PSI?.toBoolean()) {
                run_jjb_script('cleanup_slave.sh')
                run_jjb_script('global_setup.sh')
            }
            project_lib.checkout_project(project)
            withCredentials(
                [file(credentialsId: 'ci_secrets_file', variable: 'CI_SECRETS_FILE')]
            ) {
                try {
                    withEnv(["PROJECT=$project.name", "STD_VERSION=$project.branch"]) {
                        run_jjb_script('project_setup.sh')
                    }
                } catch(AbortException) {
                    // A temporary solution to debug and follow up with
                    // https://ovirt-jira.atlassian.net/browse/OVIRT-2504
                    emailext(
                        subject: "[JENKINS] Failed to setup proejct ${env.JOB_NAME}",
                        body: [
                            "Failed to run project_setup.sh for:",
                            "${currentBuild.displayName}.",
                            "It probably means that docker_cleanup.py failed.",
                            "This step doesn't fail the job, but we do collect",
                            "data about such failures to find the root cause.",
                            "Infra owner, ensure that we're not running out of",
                            "disk space on ${env.NODE_NAME}.",
                        ].join("\n"),
                        to: 'infra@ovirt.org',
                        mimeType: 'text/plain'
                    )
                }
            }
            if(job.is_poll_job) {
                project_lib.update_project_upstream_sources(project)
            }
            def mirrors_file
            if(mirrors) {
                mirrors_file = "${pwd()}/mirrors.yaml"
                writeFile file: mirrors_file, text: mirrors
            }
            if (!env.RUNNING_IN_PSI?.toBoolean()) {
                run_std_ci_in_mock(
                    project, job, report, tfr, mirrors_file, extra_sources
                )
            }
            else {
                run_std_ci_in_slave(
                    project, job, report, tfr, mirrors_file, extra_sources
                )
            }
        } finally {
            if (node.name.contains("bkr")) {
                sh(
                    label: 'Returning host to beaker',
                    returnStdout: true,
                    script: """
                        while [[ ! -f /usr/bin/return2beaker.sh ]]; do
                            sleep 60
                        done
                        /usr/bin/return2beaker.sh
                    """.stripIndent()
                )
            }
            report.status('PENDING', 'Collecting results')
            archiveArtifacts allowEmptyArchive: true, \
                artifacts: "${get_job_dir(job)}/**"
            junit keepLongStdio: true, allowEmptyResults: true, \
                testResults: "${get_job_dir(job)}/**/*test*xml"
        }
        // The only way we can get to these lines is if nothing threw any
        // exceptions so far. This means the job was successful.
        if (!env.RUNNING_IN_PSI?.toBoolean()) {
            run_jjb_script('global_setup_apply.sh')
        }
        success = true
    } finally {
        if(success) {
            report.status('SUCCESS', 'Test is successful')
        } else if (tfr.test_failed) {
            report.status('FAILURE', 'Test script failed')
        } else {
            report.status('ERROR', 'Testing system error')
        }
    }
}

def run_std_ci_in_mock(
    project, job, report, TestFailedRef tfr, mirrors=null, extra_sources=null
) {
    try {
        run_jjb_script('mock_setup.sh')
        dir(project.clone_dir_name) {
            if(extra_sources) {
                def extra_sources_file = "${pwd()}/extra_sources"
                writeFile file: extra_sources_file, text: extra_sources
                println "extra_sources file was created: ${extra_sources_file}"
            }
            report.status('PENDING', 'Running test')
            withHook('mock_runner') {
                // Set flag to 'true' to indicate that exception from this point
                // means the test failed and not the CI system
                tfr.test_failed = true
                mock_runner(job.script, job.distro, job.arch, job.timeout, mirrors)
                // If we got here (no exception thrown so far), the test did not
                // fail
                tfr.test_failed = false
            }
            invoke_pusher(
                project, 'push',
                args: [
                    '--if-not-exists',
                    "--unless-hash=${env.BUILD_TAG}",
                    project.branch
                ]
            )
        }
    } finally {
        report.status('PENDING', 'Collecting results')
        withCredentials([usernamePassword(
            credentialsId: 'ci-containers_intermediate-repository',
            passwordVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD',
            usernameVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME'
        )]) {
            withEnv([
                "PROJECT=${project.name}",
                "EXPORTED_ARTIFACTS=${env.WORKSPACE}/${get_job_dir(job)}",
            ]) {
                run_jjb_script('collect_artifacts.sh')
            }
        }
        report.status('PENDING', 'Cleaning up')
        run_jjb_script('mock_cleanup.sh')
    }
}

def run_std_ci_in_slave(project, job, report, tfr, mirrors_file, extra_sources) {
    try {
        dir(project.clone_dir_name) {
            report.status('PENDING', 'Running test')
            if(extra_sources) {
                def extra_sources_file = "${pwd()}/extra_sources"
                writeFile file: extra_sources_file, text: extra_sources
                println "extra_sources file was created: ${extra_sources_file}"
            }
            run_code(job.script, job.distro, job.arch, mirrors_file)
            invoke_pusher(
                project, 'push',
                args: [
                    '--if-not-exists',
                    "--unless-hash=${env.BUILD_TAG}",
                    project.branch
                ]
            )
        }
    }
    finally {
        report.status('PENDING', 'Collecting results')
        withCredentials([usernamePassword(
            credentialsId: 'ci-containers_intermediate-repository',
            passwordVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD',
            usernameVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME'
        )]) {
            withEnv([
                "PROJECT=${project.name}",
                "EXPORTED_ARTIFACTS=${env.WORKSPACE}/${get_job_dir(job)}",
            ]) {
                run_jjb_script('collect_artifacts.sh')
            }
        }
    }
}

def run_code(script, distro, arch, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    mirrors_arg=''
    if(mirrors != null) {
        mirrors_arg = "--try-mirrors '$mirrors'"
    }
    timeout(time: 180) {
        sh """
            ../jenkins/jobs/confs/shell-scripts/run_code.sh \\
                --execute-script "$script" \\
                --secrets-file "$WORKSPACE/std_ci_secrets.yaml" \\
                $mirrors_arg
        """
    }
}

def mock_runner(script, distro, arch, timeout, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    mirrors_arg=''
    if(mirrors != null) {
        mirrors_arg = "--try-mirrors '$mirrors'"
    }
    def timeoutcmd = timeout != "unlimited" ? "--timeout-duration ${timeout}" : ""
    sh """
        ../jenkins/mock_configs/mock_runner.sh \\
            --execute-script "$script" \\
            --mock-confs-dir ../jenkins/mock_configs \\
            --secrets-file "$WORKSPACE/std_ci_secrets.yaml" \\
            --try-proxy \\
            ${timeoutcmd} \\
            $mirrors_arg \
            "${distro}.*${arch}"
    """
}

def get_job_name(Map job) {
    if(job.substage == "default")
        return "${job.stage}.${job.distro}.${job.arch}"
    return "${job.stage}.${job.substage}.${job.distro}.${job.arch}"
}

def invoke_pusher(Map options=[:], project, String cmd) {
    sshagent(['std-ci-git-push-credentials']) {
        return sh(
            script: """
                logs_dir="exported-artifacts/pusher_logs"
                mkdir -p "\$logs_dir"
                PYTHONPATH="\${PYTHONPATH:+\$PYTHONPATH:}${env.WORKSPACE}/jenkins" \
                    ${env.WORKSPACE}/jenkins/stdci_tools/pusher.py \
                    --verbose --log="\$logs_dir/pusher_${cmd}.log" \
                    ${cmd} ${options.get('args', []).join(' ')}
            """,
            returnStatus: options.get('returnStatus', false)
        )
    }
}


class PipelineReporter extends CpsScript implements Serializable {
    class ThreadReporter extends CpsScript implements Serializable {
        def job
        def pipeline_report

        def ThreadReporter(parent, stdci_job) {
            job = stdci_job
            pipeline_report = parent
        }
        def status(status, message) {
            pipeline_report.job_status(job, status, message)
        }

        // run() is an abstract method defined by CpsScript so we must define it
        def run() {}
    }

    def stdci_summary_lib
    def project
    def threads_summary
    def get_job_name
    def get_job_dir

    def PipelineReporter(parent, stdci_project) {
        stdci_summary_lib = parent.stdci_summary_lib
        get_job_name = { parent.get_job_name(it) }
        get_job_dir = { parent.get_job_dir(it) }
        project = stdci_project
        threads_summary = [:]
    }

    def mk_thread_reporter(stdci_job) {
        return new ThreadReporter(this, stdci_job)
    }

    def job_status(job, status, message) {
        String ctx = get_job_name(job)
        threads_summary[ctx] = [
            result: status,
            message: message,
        ]
        // if we link to the STDCI summary, allocate node to generate it if we
        // don't have one already
        def allocate_node = (job.reporting.style == 'stdci')
        stdci_summary_lib.generate_summary(project, threads_summary, null, allocate_node)
        // Only notify the project after we generate the report so that if the
        // report is linked to it, the link is valid.
        String report_url = get_report_url(job, status)
        project.notify(ctx, status, message, null, report_url)
    }

    def get_report_url(job, status) {
        String report_style = job.reporting.style
        switch (report_style) {
            case 'default':
                return null
            case 'classic':
                return env.BUILD_URL
            case 'blueocean':
                return "${env.BUILD_URL}display/redirect"
            case 'stdci':
                return "${env.BUILD_URL}artifact/ci_build_summary.html"
            case 'plain':
                return [
                    env.BUILD_URL,
                    "artifact/${get_job_dir(job)}",
                    "/mock_logs/script/stdout_stderr.log",
                ].join('')
        }
    }

    def no_jobs() {
        stdci_summary_lib.generate_summary(project, [:])
    }

    // run() is an abstract method defined by CpsScript so we must define it
    def run() {}
}


@NonCPS
def remove_blacklisted_jobs(jobs) {
    def blacklisted_archs = (env.STDCI_BLACKLISTED_ARCHS ?: '').split(':') as Set
    def blacklisted_distros = (env.STDCI_BLACKLISTED_DISTROS ?: '').split(':') as Set
    print "Blacklisted: archs: $blacklisted_archs distros: $blacklisted_distros"
    jobs.removeAll { job ->
        (job.arch in blacklisted_archs) || (job.distro in blacklisted_distros)
    }
    jobs.removeAll { job ->
        (job.runtime_reqs?.jenkinsmaster == 'psi' && !env.RUNNING_IN_PSI?.toBoolean()) ||
        (job.runtime_reqs?.jenkinsmaster == 'upstream' && env.RUNNING_IN_PSI?.toBoolean())
    }
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
