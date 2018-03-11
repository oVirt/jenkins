// standard-stage.groovy - Pipeling-based STD-CI implementation
//
String std_ci_stage
Project project
def jobs
def queues

def on_load(loader){
    // Copy methods from loader to this script
    metaClass.checkout_repo = loader.&checkout_repo
    metaClass.checkout_jenkins_repo = loader.&checkout_jenkins_repo
    metaClass.run_jjb_script = loader.&run_jjb_script
}

def loader_main(loader) {
    stage('Detecting STD-CI jobs') {
        std_ci_stage = get_stage_name()
        project = get_project()
        check_whitelist(project)
        currentBuild.displayName += " ${project.name} [$std_ci_stage]"

        checkout_project(project)
        dir(project.name) {
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
    try {
        stage('Invoking jobs') {
            run_std_ci_jobs(project, jobs)
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
            }
        }
    }
}

@NonCPS
def get_stage_name() {
    if('STD_CI_STAGE' in params) {
        return params.STD_CI_STAGE
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

class Project implements Serializable {
    String clone_url
    String name
    String branch
    String refspec
    String head
    String change_owner
    def notify = \
        { context, status, short_msg=null, long_msg=null, url=null -> }
    def get_queue_build_args = null
    def check_whitelist = { -> true }
}

def get_project() {
    if('STD_CI_CLONE_URL' in params) {
        get_project_from_params()
    } else if('ghprbGhRepository' in params) {
        get_project_from_github_pr()
    } else if(params.x_github_event == 'push') {
        get_project_from_github_push()
    } else if('GERRIT_EVENT_TYPE' in params) {
        get_project_from_gerrit()
    } else {
        error "Cannot detect project from trigger or parameter information!"
    }
}

def check_whitelist(Project project) {
    if(!project.check_whitelist()){
        currentBuild.result = 'NOT_BUILT'
        error("User $project.change_owner is not whitelisted")
    }
}

def is_gerrit_change_merged() {
    // Check if the change is merged. Requires Gerrit Trigger env params!
    def change_merged_sh = readFile("jenkins/scripts/check_if_merged.sh")
    def is_merged = sh returnStatus: true, script: change_merged_sh
    return is_merged == 0
}

def get_project_from_gerrit() {
    Project project = new Project(
        clone_url: "https://${params.GERRIT_NAME}/${params.GERRIT_PROJECT}",
        name: params.GERRIT_PROJECT.tokenize('/')[-1],
        branch: params.GERRIT_BRANCH,
        refspec: params.GERRIT_REFSPEC,
        change_owner: params.GERRIT_PATCHSET_UPLOADER_EMAIL,
    )
    if(!is_gerrit_change_merged()) {
        // Change is not merged. Initialize whitelist checking function
        project.check_whitelist = {
            def whitelist_sh = readFile("jenkins/scripts/whitelist_filter.sh")
            def is_whitelisted = sh returnStatus: true, script: whitelist_sh
            return is_whitelisted == 0
        }
        return project
    }
    // Change is merged. Initialize queue build args getter
    project.get_queue_build_args = { String queue ->
        get_generic_queue_build_args(
            queue, project.name, project.branch, project.head,
        )
    }
    return project
}

def get_project_from_params() {
    return new Project(
        clone_url: params.STD_CI_CLONE_URL,
        name: params.STD_CI_CLONE_URL.tokenize('/')[-1] - ~/.git$/,
        refspec: params.STD_CI_REFSPEC,
    )
}

def get_project_from_github_pr() {
    return get_github_project(
        params.ghprbGhRepository.tokenize('/')[-2],
        params.ghprbGhRepository.tokenize('/')[-1],
        params.ghprbTargetBranch,
        "refs/pull/${params.ghprbPullId}/merge",
        params.ghprbActualCommit,
        params.ghprbTriggerAuthorLogin
    )
}

def get_project_from_github_push() {
    Project project = get_github_project(
        params.GH_EV_REPO_owner_login,
        params.GH_EV_REPO_name,
        params.GH_EV_REF.tokenize('/')[-1],
        params.GH_EV_REF,
        params.GHPUSH_SHA,
        params.GHPUSH_PUSHER_email,
        params.GHPUSH_SHA
    )
    project.get_queue_build_args = { String queue ->
        get_generic_queue_build_args(
            queue, project.name, project.branch, project.head,
            params.GH_EV_HEAD_COMMIT_url
        )
    }
    return project
}

def get_github_project(
    String org, String repo, String branch, String test_ref, String notify_ref,
    String change_owner, String checkout_head = null
) {
    Project project = new Project(
        clone_url: "https://github.com/$org/$repo",
        name: repo,
        branch: branch,
        refspec: test_ref,
        head: checkout_head,
        change_owner: change_owner,
    )
    if(env.SCM_NOTIFICATION_CREDENTIALS) {
        def last_status = null
        project.notify = { context, status, short_msg=null, long_msg=null, url=null ->
            try {
                githubNotify(
                    credentialsId: env.SCM_NOTIFICATION_CREDENTIALS,
                    account: org, repo: repo, sha: notify_ref,
                    context: context,
                    status: status, description: short_msg, targetUrl: url
                )
            } catch(Exception e) {
                // Only retry sending notification if status has changed
                if(last_status != status) {
                    retry(5) {
                        // We might be blocked by GitHub rate limit so wait a while
                        // before retrying
                        sleep 1
                        githubNotify(
                            credentialsId: env.SCM_NOTIFICATION_CREDENTIALS,
                            account: org, repo: repo, sha: notify_ref,
                            context: context,
                            status: status, description: short_msg, targetUrl: url
                        )
                    }
                }
            }
            last_status = status
        }
    }
    return project
}

def get_generic_queue_build_args(
    String queue, String project, String branch, String sha, String url=null
) {
    def json_file = "${queue}_build_args.json"
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from os import environ
            from scripts.change_queue import JenkinsChangeQueueClient
            from scripts.change_queue.changes import (
                GitMergedChange, GerritMergedChange
            )

            jcqc = JenkinsChangeQueueClient('${queue}')
            if 'GERRIT_EVENT_TYPE' in environ:
                change = GerritMergedChange.from_jenkins_env()
            else:
                change = GitMergedChange(
                    '$project', '$branch', '$sha'${url ? ", '$url'" : ""}
                )
            change.set_current_build_from_env()
            jcqc.add(change).as_pipeline_build_step_json('${json_file}')
        """.stripIndent()
    }
    def build_args = readJSON(file: json_file)
    return build_args
}

def checkout_project(Project project) {
    checkout_repo(project.name, project.refspec, project.clone_url, project.head)
}

def get_std_ci_job_properties(Project project, String std_ci_stage) {
    def stdci_job_properties = "jobs_for_${std_ci_stage}.yaml"
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from scripts.stdci_dsl.api import (
                get_formatted_threads, setupLogging
            )

            setupLogging()
            stdci_config = get_formatted_threads(
                'pipeline_dict', '${project.name}', '${std_ci_stage}'
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

def get_std_ci_queues(Project project, Map job_properties) {
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

def mk_enqueue_change_branch(Project project, String queue) {
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

def run_std_ci_jobs(project, jobs) {
    def branches = [:]
    for(job in jobs) {
        branches[get_job_name(job)] = mk_std_ci_runner(project, job)
    }
    parallel branches
}

def mk_std_ci_runner(project, job) {
    return {
        String ctx = get_job_name(job)
        project.notify(ctx, 'PENDING', 'Allocating runner node')
        String node_label = get_std_ci_node_label(job)
        if(node_label.empty) {
            print "This script has no special node requirements"
        } else {
            print "This script required nodes with label: $node_label"
        }
        node(node_label) {
            run_std_ci_on_node(project, job, get_job_dir(job))
        }
    }
}

def get_job_dir(job) {
    return get_job_name(job)
}

@NonCPS
def get_std_ci_node_label(job) {
    def label_conditions = []
    if(job.runtime_reqs?.support_nesting_level >= 2) {
        label_conditions << 'integ-tests'
    }
    if(job.runtime_reqs?.support_nesting_level == 1) {
        label_conditions << 'nested'
    }
    if(job.runtime_reqs?.host_distro =~ /^(?i)same$/) {
        label_conditions << job.distro
    }
    if(job.runtime_reqs?.host_distro =~ /^(?i)newer$/) {
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

class TestFailedRef implements Serializable {
    // Flag used to indicate that the actual test failed and not something else
    // Its inside a class so we can pass it by reference by passing object
    // instance around
    Boolean test_failed = false
}

def run_std_ci_on_node(project, job, stash_name) {
    TestFailedRef tfr = new TestFailedRef()
    Boolean success = false
    String ctx = get_job_name(job)
    try {
        try {
            project.notify(ctx, 'PENDING', 'Setting up test environment')
            dir("exported-artifacts") { deleteDir() }
            checkout_jenkins_repo()
            checkout_project(project)
            run_jjb_script('cleanup_slave.sh')
            run_jjb_script('global_setup.sh')
            withCredentials(
                [file(credentialsId: 'ci_secrets_file', variable: 'CI_SECRETS_FILE')]
            ) {
                withEnv(["PROJECT=$project.name", "STD_VERSION=$project.branch"]) {
                    run_jjb_script('project_setup.sh')
                }
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
        } else if (tfr.test_failed) {
            project.notify(ctx, 'FAILURE', 'Test script failed')
        } else {
            project.notify(ctx, 'ERROR', 'Testing system error')
        }
    }
}

def run_std_ci_in_mock(Project project, def job, TestFailedRef tfr) {
    String ctx = get_job_name(job)
    try {
        run_jjb_script('mock_setup.sh')
        // TODO: Load mirros once for whole pipeline
        // unstash 'mirrors'
        // def mirrors = "${pwd()}/mirrors.yaml"
        def mirrors = null
        dir(project.name) {
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

def collect_jobs_artifacts(jobs) {
    for (ji = 0; ji < jobs.size(); ++ji) {
        def job = jobs[ji]
        def job_dir = get_job_dir(job)
        dir("exported-artifacts/$job_dir") {
            unstash job_dir
        }
    }
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
