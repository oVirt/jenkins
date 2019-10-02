// standard-stage.groovy - Pipeling-based STD-CI implementation
//

import hudson.model.ParametersAction
import org.jenkinsci.plugins.workflow.support.steps.build.RunWrapper
import groovy.transform.Field

@Field def project_lib
@Field def stdci_runner_lib

def on_load(loader){
    project_lib = loader.load_code('libs/stdci_project.groovy')
    stdci_runner_lib = loader.load_code('libs/stdci_runner.groovy')
    def build_params_lib = loader.load_code('libs/build_params.groovy')

    modify_build_parameter = build_params_lib.&modify_build_parameter
}

@Field String std_ci_stage
@Field def project
@Field def jobs
@Field def queues
@Field def previous_build
@Field Boolean wait_for_previous_build

def loader_main(loader) {
    stage('Detecting STD-CI jobs') {
        std_ci_stage = get_stage_name()

        project = project_lib.get_project()
        set_gerrit_trigger_voting(project, std_ci_stage)
        check_whitelist(project)
        currentBuild.displayName += " ${project.name} [$std_ci_stage]"

        project_lib.checkout_project(project)
        save_stdci_info(std_ci_stage, project)
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
        save_gate_info(job_properties.is_gated_project, queues)
        if(!queues.empty && std_ci_stage != 'build-artifacts') {
            // If we need to submit the change the queues, make sure we
            // generate builds
            build_job_properties = get_std_ci_job_properties(
                project, 'build-artifacts'
            )
            jobs += get_std_ci_jobs(build_job_properties)
        }
        stdci_runner_lib.remove_blacklisted_jobs(jobs)
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
    previous_build = null
    wait_for_previous_build = false
    if(std_ci_stage == 'build-artifacts') {
        // Try to find previous build of the same commit
        stage('Looking for existing build') {
            previous_build = find_oldest_same_build(std_ci_stage, project)
            if(previous_build == null) {
                echo "No previous build, would run builds here"
                return
            }
            echo "Found previous build of same commit: ${previous_build.number}"
            if(previous_build.result == null) {
                wait_for_previous_build = true
            } else {
                copy_previos_build_artifacts(previous_build)
            }
        }
    }
}

def main() {
    if(std_ci_stage == 'build-artifacts') {
        stage('Downloading existing build') {
            if(previous_build != null) {
                if(wait_for_previous_build) {
                    waitUntil {
                        echo "Waiting for build ${previous_build.number} to finish"
                        return previous_build.result != null
                    }
                    node(env?.LOADER_NODE_LABEL) {
                        copy_previos_build_artifacts(previous_build)
                    }
                } else {
                    echo "Done already."
                }
            } else {
                echo "Skipped - no previous build"
            }
        }
    }
    if(previous_build != null) {
        return
    }
    tag_poll_job(jobs)
    stage('Invoking jobs') {
        stdci_runner_lib.run_std_ci_jobs(project, jobs)
    }
    if(!queues.empty && job_properties.is_gated_project) {
        stage('Deploying to gated repo') {
            deploy_to_gated(project, queues)
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
            import yaml
            from scripts.stdci_dsl.api import (
                get_formatted_threads, setupLogging
            )
            from scripts.zuul_helpers import is_gated_project

            setupLogging()
            stdci_config = get_formatted_threads(
                'pipeline_dict', '${project.clone_dir_name}', '${std_ci_stage}'
            )

            # Inject gating info into STDCI config
            stdci_config_parsed = yaml.safe_load(stdci_config)
            stdci_config_parsed['is_gated_project'] = \
                is_gated_project('${project.clone_dir_name}')
            stdci_config = yaml.safe_dump(
                stdci_config_parsed, default_flow_style=False
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

def save_stdci_info(std_ci_stage, project) {
    modify_build_parameter('STD_CI_STAGE', std_ci_stage)
    project_lib.save_project_info(project)
}

@NonCPS
def is_same_stdci_build(std_ci_stage, project, build) {
    def build_params = build.getAction(hudson.model.ParametersAction)
    return (
        build_params.getParameter('STD_CI_STAGE')?.value == std_ci_stage &&
        project_lib.is_same_project_build(project, build)
    )
}

@NonCPS
def find_oldest_same_build(std_ci_stage, project) {
    def same_builds = currentBuild.rawBuild.parent.builds.findAll { build ->
        (build.number < currentBuild.number) && (
            build.isBuilding() ||
            build.result.isBetterOrEqualTo(hudson.model.Result.SUCCESS)
        ) &&
        is_same_stdci_build(std_ci_stage, project, build)
    }
    if(same_builds.isEmpty()) {
        return null
    }
    return new RunWrapper(same_builds.last(), false)
}

def copy_previos_build_artifacts(previous_build) {
    if(previous_build.result != 'SUCCESS') {
        error 'Previous build failed'
    }
    echo "Getting artifacts from previous build instead of building"
    dir('imported-artifacts') {
        deleteDir()
        copyArtifacts(
            fingerprintArtifacts: true,
            optional: true,
            projectName: env.JOB_NAME,
            selector: specific(previous_build.id),
            target: '.',
        )
        archiveArtifacts '**/*'
    }
}

def deploy_to_gated(project, queues) {
    def branches = [:]
    for(queue in queues) {
        branches[queue] = mk_deploy_to_gated_branch(project, queue)
   }
    try {
        parallel branches
    } catch(Exception e) {
        // Make deploy failures not fail the whole job but still show up in
        // yellow in Jenkins
        currentBuild.result = 'UNSTABLE'
    }
}

def mk_deploy_to_gated_branch(project, String queue) {
    return {
        String ctx = "deploy to: gated-$queue"
        try {
            project.notify(ctx, 'PENDING', 'Deploying change to gated repo')
            build "deploy-to-gated-$queue"
            project.notify(ctx, 'SUCCESS', 'Change deployed')
        } catch(Exception eb) {
            project.notify(ctx, 'FAILURE', 'Failed to deploy - does repo exist?')
            throw eb
        }
    }
}

def save_gate_info(is_gated_project, queues) {
    def value
    // Save information about which gated repos are we deploying to, so gating
    // jobs can avoid waiting for builds they do not need to test
    if(is_gated_project) {
        value = queues.join(' ')
    } else {
        value = '__none__'
    }
    modify_build_parameter('GATE_DEPLOYMENTS', value)
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
