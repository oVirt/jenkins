// standard-stage.groovy - Pipeling-based STD-CI implementation
//

import hudson.model.ParametersAction

def project_lib
def stdci_runner_lib

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
    metaClass.load_code = {
        code_file, load_as=null -> loader.metaClass.invokeMethod(
            loader, 'load_code', [code_file, load_as]
        )
    }
    project_lib = loader.load_code('libs/stdci_project.groovy', this)
    stdci_runner_lib = loader.load_code('libs/stdci_runner.groovy', this)
}

def loader_main(loader) {
    stage('Detecting STD-CI jobs') {
        std_ci_stage = get_stage_name()

        project = project_lib.get_project()
        set_gerrit_trigger_voting(project, std_ci_stage)
        check_whitelist(project)
        currentBuild.displayName += " ${project.name} [$std_ci_stage]"

        project_lib.checkout_project(project)
        set_gerrit_automerge(project, std_ci_stage)
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
                "\n- ${stdci_runner_lib.get_job_name(job)}"
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
    tag_poll_job(jobs)
    stage('Invoking jobs') {
        stdci_runner_lib.run_std_ci_jobs(project, jobs)
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
        if (params.GERRIT_EVENT_COMMENT_TEXT =~ /(?m)^ci +(please +)?(test|check)( +please)?$/) {
            return 'check-patch'
        } else if (params.GERRIT_EVENT_COMMENT_TEXT =~ /(?m)^ci +(please +)?build( +please)?$/) {
            return 'build-artifacts'
        } else if (params.GERRIT_EVENT_COMMENT_TEXT =~ /(?m)^ci +(please +)?re-merge( +please)?$/) {
            return 'check-merged'
        }
    }
    return null
}

def set_gerrit_trigger_voting(project, stage_name) {
    if(stage_name != "check-patch") { return }
    modify_build_parameter(
        "GERRIT_TRIGGER_CI_VOTE_LABEL",
        "--label Continuous-Integration=<CODE_REVIEW>"
    )
}

def set_gerrit_automerge(project, stage_name) {
    if(stage_name != "check-patch") { return }
    dir(project.clone_dir_name) {
        if(stdci_runner_lib.invoke_pusher(project, 'can_merge', returnStatus: true) == 0) {
            modify_build_parameter(
                "GERRIT_TRIGGER_CI_VOTE_LABEL",
                "--label Continuous-Integration=<CODE_REVIEW>" +
                " --code-review=2" +
                " --verified=1" +
                " --submit"
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
        if(params.ghprbCommentBody =~ /^ci +(please +)?build( +please)?/) {
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
        println("Job marked as poll-job: " + stdci_runner_lib.get_job_name(poll_job))
        return
    }
    println("No suitable job for poll-upstream-sources stage was found")
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
