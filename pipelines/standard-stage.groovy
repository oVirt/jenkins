// standard-stage.groovy - Pipeling-based STD-CI implementation
//

import hudson.model.ParametersAction

def project_lib
def stdci_summary_lib

String std_ci_stage
def project
def jobs
def queues

def on_load(loader){
    // Copy methods from loader to this script
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
    project_lib = loader.load_code('libs/stdci_project.groovy', this)
    stdci_summary_lib = loader.load_code('libs/stdci_summary.groovy', this)
}

def loader_main(loader) {
    stage('Detecting STD-CI jobs') {
        std_ci_stage = get_stage_name()

        project = project_lib.get_project()
        set_gerrit_trigger_voting(project, std_ci_stage)
        check_whitelist(project)
        currentBuild.displayName += " ${project.name} [$std_ci_stage]"

        project_lib.checkout_project(project)
        dir(project.clone_dir_name) {
            // This is a temporary workaround for KubeVirt project
            sh """
                [[ ! -f automation/check-patch.yaml ]] && exit 0
                cp automation/check-patch.yaml .stdci.yaml
            """
        }
        job_properties = get_std_ci_job_properties(project, std_ci_stage)
        jobs = get_std_ci_jobs(job_properties)
        queues = get_std_ci_queues(project, job_properties)
        if(!queues.empty && std_ci_stage != 'build-artifacts') {
            // If we need to submit the change the queues, make sure we
            // generate builds
            build_job_properties = get_std_ci_job_properties(
                project, 'build-artifacts'
            )
            jobs += get_std_ci_jobs(build_job_properties)
        }
        if(jobs.empty) {
            echo "No STD-CI job definitions found"
        } else {
            def job_list = "Will run ${jobs.size()} job(s):"
            job_list += jobs.collect { job ->
                "\n- ${get_job_name(job)}"
            }.join()
            print(job_list)
        }
    }
    if(!queues.empty) {
        stage('Queueing change') {
            enqueue_change(project, queues)
        }
    }
}

def main() {
    def threads_summary = [:]
    try {
        stage('Invoking jobs') {
            run_std_ci_jobs(project, jobs, threads_summary)
        }
    } finally {
        stage('Collecting results') {
            node() {
                dir("exported-artifacts") { deleteDir() }
                collect_jobs_artifacts(jobs)
                archiveArtifacts allowEmptyArchive: true, \
                    artifacts: 'exported-artifacts/**'
                junit keepLongStdio: true, allowEmptyResults: true, \
                    testResults: 'exported-artifacts/**/*xml'
                // Generate and archive the summary
                stdci_summary_lib.generate_summary(project, threads_summary)
            }
        }
    }
}

@NonCPS
def get_stage_name() {
    if('STD_CI_STAGE' in params) {
        return params.STD_CI_STAGE
    }
    if(env.STD_CI_STAGE) {
        return env.STD_CI_STAGE
    }
    def stage
    if (params.GERRIT_EVENT_TYPE){
        stage = get_stage_gerrit()
    } else {
        stage = get_stage_github()
    }
    if (stage) { return stage }
    error "Failed to detect stage from trigger event or parameters"
}

@NonCPS
def get_stage_gerrit() {
    if (params.GERRIT_EVENT_TYPE == "patchset-created" ||
        params.GERRIT_EVENT_TYPE == "draft-published") {
        return 'check-patch'
    }
    if (params.GERRIT_EVENT_TYPE == "change-merged") { return 'check-merged' }
    if (params.GERRIT_EVENT_TYPE == "comment-added") {
        if (params.GERRIT_EVENT_COMMENT_TEXT =~ /(?m)^ci test please$/) {
            return 'check-patch'
        } else if (params.GERRIT_EVENT_COMMENT_TEXT =~ /(?m)^ci build please$/) {
            return 'build-artifacts'
        } else if (params.GERRIT_EVENT_COMMENT_TEXT =~ /(?m)^ci re-merge please$/) {
            return 'check-merged'
        }
    }
    return null
}

void set_gerrit_trigger_voting(project, stage_name) {
    if(stage_name != "check-patch") { return }
    dir(project.clone_dir_name) {
        if(invoke_pusher(project, 'can_merge', returnStatus: true) == 0) {
            modify_build_parameter(
                "GERRIT_TRIGGER_CI_VOTE_LABEL",
                "--label Continuous-Integration=<CODE_REVIEW>" +
                " --code-review=2" +
                " --verified=1" +
                " --submit"
            )
        }
        else {
            modify_build_parameter(
                "GERRIT_TRIGGER_CI_VOTE_LABEL",
                "--label Continuous-Integration=<CODE_REVIEW>"
            )
        }
    }
}

@NonCPS
def modify_build_parameter(String key, String value) {
    def build = currentBuild.rawBuild
    def params_list = new ArrayList<StringParameterValue>()
    params_list.add(new StringParameterValue(key, value))
    def new_params_action = null
    def old_params_action = build.getAction(ParametersAction.class)
    if (old_params_action != null) {
        // We need to keep old params
        build.actions.remove(old_params_action)
        new_params_action = old_params_action.createUpdated(params_list)
    } else {
        new_params_action = new ParametersAction(params_list)
    }
    build.actions.add(new_params_action)
}

@NonCPS
def get_stage_github() {
    if(params.ghprbActualCommit) {
        // We assume ghprbActualCommit will always be set by the ghprb trigger,
        // so if we get here it means we got triggered by it
        if(params.ghprbCommentBody =~ /^ci build please/) {
            return 'build-artifacts'
        }
        // We run check-patch by default
        return 'check-patch'
    }
    if(params.x_github_event == 'push') { return 'check-merged' }
    return null
}

def get_std_ci_job_properties(project, String std_ci_stage) {
    def stdci_job_properties = "jobs_for_${std_ci_stage}.yaml"
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from scripts.stdci_dsl.api import (
                get_formatted_threads, setupLogging
            )

            setupLogging()
            stdci_config = get_formatted_threads(
                'pipeline_dict', '${project.clone_dir_name}', '${std_ci_stage}'
            )
            with open('${stdci_job_properties}', 'w') as conf:
                conf.write(stdci_config)
        """.stripIndent()
    }
    def cfg = readYaml file: stdci_job_properties
    return cfg
}

def get_std_ci_jobs(Map job_properties) {
    return job_properties.get('jobs')
}

def get_std_ci_global_options(Map job_properties) {
    return job_properties.get('global_config')
}

def get_std_ci_queues(project, Map job_properties) {
    if(get_stage_name() != 'check-merged') {
        // Only Enqueue on actual merge/push events
        return []
    }
    print "Checking if change should be enqueued"
    def branch_queue_map = \
        get_std_ci_global_options(job_properties).get("release_branches")
    def o = branch_queue_map.get(project.branch, [])
    if (o in Collection) {
        return o.collect { it as String } as Set
    } else {
        return [o as String]
    }
}

def enqueue_change(project, queues) {
    def branches = [:]
    for(queue in queues) {
        branches[queue] = mk_enqueue_change_branch(project, queue)
    }
    try {
        parallel branches
    } catch(Exception e) {
        // Make enqueue failures not fail the whole job but still show up in
        // yellow in Jenkins
        currentBuild.result = 'UNSTABLE'
    }
}

def mk_enqueue_change_branch(project, String queue) {
    return {
        String ctx = "enqueue to: $queue"
        def build_args
        try {
            project.notify(ctx, 'PENDING', 'Submitting change to queue')
            build_args = project.get_queue_build_args(queue)
            build_args['wait'] = true
        } catch(Exception ea) {
            project.notify(ctx, 'ERROR', 'System error')
            throw ea
        }
        try {
            build build_args
            project.notify(ctx, 'SUCCESS', 'Change submitted')
        } catch(Exception eb) {
            project.notify(ctx, 'FAILURE', 'Failed to submit - does queue exist?')
            throw eb
        }
    }
}

def get_job_name(Map job) {
    if(job.substage == "default")
        return "${job.stage}.${job.distro}.${job.arch}"
    return "${job.stage}.${job.substage}.${job.distro}.${job.arch}"
}

def run_std_ci_jobs(project, jobs, threads_summary) {
    def branches = [:]
    tag_poll_job(jobs)
    for(job in jobs) {
        branches[get_job_name(job)] = mk_std_ci_runner(threads_summary, project, job)
    }
    parallel branches
}

@NonCPS
def tag_poll_job(jobs) {
    def poll_job

    // Try to find and tag the poll job. The preferences are:
    // 1. el7/x86_64/default-substage
    // 2. el7/default-substage
    // 3. default-substage
    // Otherwise, poll will not run.
    for(job in jobs) {
            if(job.distro == "el7" &&
                job.arch == "x86_64" &&
                job.stage == "poll-upstream-sources" &&
                job.substage == "default"
            ) {
                // 1st preference found
                poll_job = job
                break
            }
            else if(job.distro == "el7" &&
                     job.stage == "poll-upstream-sources" &&
                     job.substage == "default"
            ) {
                // 2nd preference found, but we may still find 1st preference
                poll_job = job
            }
            else if(job.stage == "poll-upstream-sources" &&
                     job.substage == "default" &&
                     !poll_job) {
                // 3rd preference found, but we may still find 1st or 2nd preference
                poll_job = job
            }
    }

    if(poll_job) {
        poll_job.is_poll_job = true
        println("Job marked as poll-job: " + get_job_name(poll_job))
        return
    }
    println("No suitable job for poll-upstream-sources stage was found")
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

class TestFailedRef implements Serializable {
    // Flag used to indicate that the actual test failed and not something else
    // Its inside a class so we can pass it by reference by passing object
    // instance around
    Boolean test_failed = false
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

def invoke_pusher(Map options=[:], project, String cmd) {
    sshagent(['std-ci-git-push-credentials']) {
        return sh(
            script: """
                ${env.WORKSPACE}/jenkins/scripts/pusher.py \
                    --log --verbose --debug \
                    ${cmd} ${options.get('args', []).join(' ')}
            """,
            returnStatus: options.get('returnStatus', false)
        )
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

def collect_jobs_artifacts(jobs) {
    for (ji = 0; ji < jobs.size(); ++ji) {
        def job = jobs[ji]
        def job_dir = get_job_dir(job)
        dir("exported-artifacts/$job_dir") {
            unstash job_dir
        }
    }
}

def check_whitelist(project) {
    if(!project.check_whitelist()){
        currentBuild.result = 'NOT_BUILT'
        error("User $project.change_owner is not whitelisted")
    }
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
