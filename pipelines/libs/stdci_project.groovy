// project.groovy - Groovy library for interacting with STDCI project
//

def on_load(loader) {
    // Copy methods from loader to this script
    // Need to specify positional arguments explicitly due to a bug in Jenkins
    // where ...args syntax passes only the 1st argument.
    metaClass.checkout_repo = {
        repo_name, refspec='refs/heads/master',
        url=null, head=null, clone_dir_name=null ->
        loader.metaClass.invokeMethod(
            loader, 'checkout_repo',
            [repo_name, refspec, url, head, clone_dir_name])
    }
}

class Project implements Serializable {
    String clone_url
    String name
    String branch
    String refspec
    String head
    String change_owner
    String clone_dir_name
    String change_url = '#'
    String change_url_disabled = 'disabled'
    String change_url_title = 'View code'
    String rerun_title = 'Rebuild'
    String rerun_url
    String org
    def checkout_data
    def notify = \
        { context, status, short_msg=null, long_msg=null, url=null -> }
    def get_queue_build_args = null
    def check_whitelist = { -> true }
}

def checkout_project(Project project) {
    def checkoutData = checkout_repo(
            project.name,
            project.refspec,
            project.clone_url,
            project.head,
            project.clone_dir_name
    )
    project.checkout_data = checkoutData
    return checkoutData
}

def new_project(Map init_params) {
    init_params.branch = init_params.get('branch', 'master')
    init_params.refspec = init_params.get('refspec', 'refs/heads/master')
    init_params.clone_dir_name = init_params.get(
        'clone_dir_name', init_params.name)
    init_params.rerun_url = init_params.get(
        'rerun_url', "${env.BUILD_URL}/rebuild")
    return new Project(init_params)
}

def get_project() {
    if('STD_CI_CLONE_URL' in params) {
        get_project_from_params()
    } else if(env.STD_CI_CLONE_URL) {
        get_project_from_env()
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

def get_project_from_gerrit() {
    String project_name = params.GERRIT_PROJECT.tokenize('/')[-1]
    Project project = new Project(
            clone_url: "https://${params.GERRIT_NAME}/${params.GERRIT_PROJECT}",
            name: project_name,
            branch: params.GERRIT_BRANCH,
            refspec: params.GERRIT_REFSPEC,
            change_owner: params.GERRIT_PATCHSET_UPLOADER_EMAIL,
            clone_dir_name: get_clone_dir_name(project_name),
            change_url: params.GERRIT_CHANGE_URL,
            change_url_disabled: '', // Empty means NOT disabled
            change_url_title: 'View patch',
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
    // Change is merged. Initialize queue stdci_build args getter
    project.get_queue_build_args = { String queue ->
        get_generic_queue_build_args(
                queue, project.name, project.branch, project.head,
        )
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

def get_project_from_params() {
    String project_name = params.STD_CI_CLONE_URL.tokenize('/')[-1] - ~/.git$/
    return new Project(
            clone_url: params.STD_CI_CLONE_URL,
            name: project_name,
            refspec: params.STD_CI_REFSPEC,
            clone_dir_name: get_clone_dir_name(project_name),
            rerun_url: env.BUILD_URL + '/rebuild'
    )
}

def get_project_from_env() {
    String project_name = env.STD_CI_CLONE_URL.tokenize('/')[-1] - ~/.git$/
    return new Project(
            clone_url: env.STD_CI_CLONE_URL,
            name: project_name,
            refspec: "refs/heads/${env.STD_VERSION}",
            branch: env.STD_VERSION,
            clone_dir_name: get_clone_dir_name(project_name),
            rerun_url: env.BUILD_URL + '/rebuild'
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

def get_project_from_github_push() { Project project = get_github_project(
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
            org: org,
            branch: branch,
            refspec: test_ref,
            head: checkout_head,
            change_owner: change_owner,
            clone_dir_name: get_clone_dir_name(repo),
            change_url: params.ghprbPullLink,
            change_url_disabled: '',
            change_url_title: 'View PR',
            rerun_url: env.BUILD_URL + '/rebuild'
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

def get_clone_dir_name(String project_name) {
    if(env.CLONE_DIR_NAME) return env.CLONE_DIR_NAME
    return project_name
}

def update_project_upstream_sources(Project project) {
    dir(project.clone_dir_name) {
        def ret = sh(
                returnStatus: true,
                script: """
                echo "Updating upstream sources."
                LOGDIR="exported-artifacts/usrc_update_logs"
                mkdir -p "\$LOGDIR"

                usrc="\$WORKSPACE/jenkins/scripts/usrc.py"
                [[ -x "\$usrc" ]] || usrc="\$WORKSPACE/jenkins/scripts/usrc_local.py"

                "\$usrc" --log="\$LOGDIR/update_${project.name}.log" update --commit
                "\$usrc" --log="\$LOGDIR/get_${project.name}.log" get
            """
        )
        if(ret != 0) {
            println("Failed to update upstream sources. See logs for info.")
            currentBuild.result = 'FAILURE'
        }
    }
}

def is_gerrit_change_merged() {
    // Check if the change is merged. Requires Gerrit Trigger env params!
    def change_merged_sh = readFile("jenkins/scripts/check_if_merged.sh")
    def is_merged = sh returnStatus: true, script: change_merged_sh
    return is_merged == 0
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
