// groovy - Pipeline wrapper for mock_runner
//

def project_lib
def stdci_summary_lib

class TestFailedRef implements Serializable {
    // Flag used to indicate that the actual test failed and not something else
    // Its inside a class so we can pass it by reference by passing object
    // instance around
    Boolean test_failed = false
}

def on_load(loader) {
    metaClass.run_jjb_script = { ...args ->
        loader.metaClass.invokeMethod(loader, 'run_jjb_script', args)
    }
    metaClass.checkout_jenkins_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_jenkins_repo', args)
    }
    // Need to specify positional arguments explicitly due to a bug in Jenkins
    // where ...args syntax passes only the 1st argument.
    metaClass.checkout_repo = {
        repo_name, refspec='heads/refs/master', url=null, head=null, clone_dir_name=null ->
        loader.metaClass.invokeMethod(
            loader, 'checkout_repo',
            [repo_name, refspec, url, head, clone_dir_name])
    }
    project_lib = loader.project_lib
    stdci_summary_lib = loader.load_code('libs/stdci_summary.groovy', this)
}

def run_std_ci_jobs(project, jobs) {
    def branches = [:]
    def threads_summary = [:]
    try {
        for(job in jobs) {
            branches[get_job_name(job)] = mk_std_ci_runner(
                threads_summary, project, job)
        }
        parallel branches
    } finally {
        // Collect results
        println "+====================+"
        println "| Collecting results |"
        println "+====================+"
        node() {
            dir("exported-artifacts") { deleteDir() }
            collect_jobs_artifacts(jobs)
            archiveArtifacts allowEmptyArchive: true, \
                artifacts: 'exported-artifacts/**'
            junit keepLongStdio: true, allowEmptyResults: true, \
                testResults: 'exported-artifacts/**/*xml'
            stdci_summary_lib.generate_summary(project, threads_summary)
        }
    }
}

def collect_jobs_artifacts(jobs) {
    for (ji = 0; ji < jobs.size(); ++ji) {
        def job = jobs[ji]
        def job_dir = get_job_dir(job)
        dir("exported-artifacts/$job_dir") {
            unstash job_dir
        }
    }
}

def mk_std_ci_runner(threads_summary, project, job) {
    return {
        String ctx = get_job_name(job)
        project.notify(ctx, 'PENDING', 'Allocating runner node')
        String node_label = get_std_ci_node_label(project, job)
        if(node_label.empty) {
            print "This script has no special node requirements"
        } else {
            print "This script required nodes with label: $node_label"
        }
        node(node_label) {
            run_std_ci_on_node(threads_summary, project, job, get_job_dir(job))
        }
    }
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
    if(job.runtime_reqs?.supportnestinglevel >= 2) {
        label_conditions << 'integ-tests'
    }
    if(job.runtime_reqs?.supportnestinglevel == 1) {
        label_conditions << 'nested'
    }
    if(job.runtime_reqs?.hostdistro =~ /^(?i)same$/) {
        label_conditions << job.distro
    }
    if(job.runtime_reqs?.hostdistro =~ /^(?i)newer$/) {
        String[] host_distros = [
            'el6', 'el7', 'fc24', 'fc25', 'fc26', 'fc27', 'fc28'
        ]
        int dist_idx = host_distros.findIndexOf { it == job.distro }
        if(dist_idx < 0) {
            throw new Exception("Can't find newer distros for ${job.distro}")
        }
        String[] job_distros = host_distros[dist_idx..<host_distros.size()]
        label_conditions << "(${job_distros.join(' || ')})"
    }
    if (job.arch != "x86_64") {
        label_conditions << job.arch
    }
    return label_conditions.join(' && ')
}


def run_std_ci_on_node(threads_summary, project, job, stash_name) {
    TestFailedRef tfr = new TestFailedRef()
    Boolean success = false
    String ctx = get_job_name(job)
    try {
        try {
            project.notify(ctx, 'PENDING', 'Setting up test environment')
            dir("exported-artifacts") { deleteDir() }
            checkout_jenkins_repo()
            project_lib.checkout_project(project)
            run_jjb_script('cleanup_slave.sh')
            run_jjb_script('global_setup.sh')
            withCredentials(
                [file(credentialsId: 'ci_secrets_file', variable: 'CI_SECRETS_FILE')]
            ) {
                withEnv(["PROJECT=$project.name", "STD_VERSION=$project.branch"]) {
                    run_jjb_script('project_setup.sh')
                }
            }
            if(job.is_poll_job) {
                project_lib.update_project_upstream_sources(project)
            }
            run_std_ci_in_mock(project, job, tfr)
        } finally {
            project.notify(ctx, 'PENDING', 'Collecting results')
            dir("exported-artifacts") {
                stash includes: '**', name: stash_name
            }
        }
        // The only way we can get to these lines is if nothing threw any
        // exceptions so far. This means the job was successful.
        run_jjb_script('global_setup_apply.sh')
        success = true
    } finally {
        if(success) {
            project.notify(ctx, 'SUCCESS', 'Test is successful')
            threads_summary[ctx] = [
                result: 'SUCCESS',
                message: 'Test is successful',
            ]
        } else if (tfr.test_failed) {
            project.notify(ctx, 'FAILURE', 'Test script failed')
            threads_summary[ctx] = [
                result: 'FAILURE',
                message: 'Test script failed',
            ]
        } else {
            project.notify(ctx, 'ERROR', 'Testing system error')
            threads_summary[ctx] = [
                result: 'ERROR',
                message: 'Testing system error',
            ]
        }
    }
}

def run_std_ci_in_mock(project, def job, TestFailedRef tfr) {
    String ctx = get_job_name(job)
    try {
        run_jjb_script('mock_setup.sh')
        // TODO: Load mirros once for whole pipeline
        // unstash 'mirrors'
        // def mirrors = "${pwd()}/mirrors.yaml"
        def mirrors = null
        dir(project.clone_dir_name) {
            project.notify(ctx, 'PENDING', 'Running test')
            // Set flag to 'true' to indicate that exception from this point
            // means the test failed and not the CI system
            tfr.test_failed = true
            timeout(time: 2, unit: 'HOURS') {
                mock_runner(job.script, job.distro, job.arch, mirrors)
            }
            // If we got here (no exception thrown so far), the test did not
            // fail
            tfr.test_failed = false
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
        project.notify(ctx, 'PENDING', 'Collecting results')
        withCredentials([usernamePassword(
            credentialsId: 'ci-containers_intermediate-repository',
            passwordVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD',
            usernameVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME'
        )]) {
            withEnv(["PROJECT=${project.name}"]) {
                run_jjb_script('collect_artifacts.sh')
            }
        }
        project.notify(ctx, 'PENDING', 'Cleaning up')
        run_jjb_script('mock_cleanup.sh')
    }
}

def mock_runner(script, distro, arch, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    mirrors_arg=''
    if(mirrors != null) {
        mirrors_arg = "--try-mirrors '$mirrors'"
    }
    sh """
        ../jenkins/mock_configs/mock_runner.sh \\
            --execute-script "$script" \\
            --mock-confs-dir ../jenkins/mock_configs \\
            --secrets-file "$WORKSPACE/std_ci_secrets.yaml" \\
            --try-proxy \\
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
                ${env.WORKSPACE}/jenkins/scripts/pusher.py \
                    --verbose --log="\$logs_dir/pusher_${cmd}.log" \
                    ${cmd} ${options.get('args', []).join(' ')}
            """,
            returnStatus: options.get('returnStatus', false)
        )
    }
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
