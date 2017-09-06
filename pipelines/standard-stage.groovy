// standard-stage.groovy - Pipeling-based STD-CI implementation
//
String std_ci_stage
Project project
def jobs

def loader_main(loader) {
    // Copy methods from loader to this script
    metaClass.checkout_repo = loader.&checkout_repo
    metaClass.checkout_jenkins_repo = loader.&checkout_jenkins_repo

    stage('Detecting STD-CI jobs') {
        std_ci_stage = get_stage_name()
        project = get_project()
        currentBuild.displayName += " ${project.name} [$std_ci_stage]"

        jobs = get_std_ci_jobs(project, std_ci_stage)
        if(jobs.empty) {
            return "No STD-CI job definitions found"
        } else {
            def job_list = "Will run ${jobs.size()} job(s):"
            job_list += jobs.collect { job ->
                "\n- ${job.stage}.${job.distro}.${job.arch}"
            }.join()
            print(job_list)
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
    if(params.ghprbActualCommit) {
        // We assume ghprbActualCommit will always be set by the ghprb trigger,
        // so if we get here it means we got triggered by it
        if(params.ghprbCommentBody =~ /^ci build please/) {
            return 'build-artifacts'
        }
        // We run check-patch by default
        return 'check-patch'
    }
    error "Failed to detect stage from trigger event or parameters"
}

class Project implements Serializable {
    String clone_url
    String name
    String refspec
    def notify = \
        { context, status, short_msg=null, long_msg=null, url=null -> }
}

def get_project() {
    if('STD_CI_CLONE_URL' in params) {
        get_project_from_params()
    } else if('ghprbGhRepository' in params) {
        get_project_from_github_pr()
    } else {
        error "Cannot detect project from trigger or paarmeter information!"
    }
}

def get_project_from_params() {
    return new Project(
        clone_url: params.STD_CI_CLONE_URL,
        name: params.STD_CI_CLONE_URL.tokenize('/')[-1] - ~/.git$/,
        refspec: params.STD_CI_REFSPEC,
    )
}

def get_project_from_github_pr() {
    Project project = new Project(
        clone_url: "https://github.com/${params.ghprbGhRepository}",
        name: params.ghprbGhRepository.tokenize('/')[-1],
        refspec: "refs/pull/${params.ghprbPullId}/merge",
    )
    if(env.SCM_NOTIFICATION_CREDENTIALS) {
        def account = params.ghprbGhRepository.tokenize('/')[-2]
        def repo = params.ghprbGhRepository.tokenize('/')[-1]
        def sha = params.ghprbActualCommit
        def last_status = null
        project.notify = { context, status, short_msg=null, long_msg=null, url=null ->
            try {
                githubNotify(
                    credentialsId: env.SCM_NOTIFICATION_CREDENTIALS,
                    account: account, repo: repo, sha: sha,
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
                            account: account, repo: repo, sha: sha,
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

def checkout_project(Project project) {
    checkout_repo(project.name, project.refspec, project.clone_url)
}

def get_std_ci_jobs(project, std_ci_stage) {
    checkout_project(project)
    dir(project.name) {
        def jobs = []
        def distros = get_std_ci_distros(std_ci_stage)
        for(di = 0; di < distros.size(); ++di) {
            def distro = distros[di]
            def archs = get_std_ci_archs(std_ci_stage, distro)
            for(ai = 0; ai < archs.size(); ++ai) {
                def arch = archs[ai]
                def runtime_reqs = \
                    get_std_ci_runtime_reqs(std_ci_stage, distro, arch)
                def script = get_std_ci_script(std_ci_stage, distro, arch)
                if(script) {
                    jobs << [
                        stage: std_ci_stage,
                        distro: distro,
                        arch: arch,
                        runtime_reqs: runtime_reqs,
                        script: script,
                    ]
                }
            }
        }
        return jobs
    }
}

def get_std_ci_distros(String std_ci_stage) {
    print "Looking up distros for running $std_ci_stage"
    def distros = get_std_ci_list(["${std_ci_stage}.distros", 'distros'])
    return distros.empty ? ['el7'] : distros
}

def get_std_ci_archs(String std_ci_stage, String distro) {
    print "Lookng up $distro architectures for $std_ci_stage"
    def archs = get_std_ci_list([
        "${std_ci_stage}.${distro}.archs",
        "${std_ci_stage}.archs",
        'archs',
    ])
    return archs.empty ? ['x86_64'] : archs
}

def get_std_ci_runtime_reqs(String std_ci_stage, String distro, String arch) {
    print "Looking up runtime_requirements for $std_ci_stage on $distro/$arch"
    return get_std_ci_dict([
        "${std_ci_stage}.${distro}.${arch}.runtime_requirements",
        "${std_ci_stage}.${distro}.runtime_requirements",
        "${std_ci_stage}.${arch}.runtime_requirements",
        "${std_ci_stage}.runtime_requirements",
        "runtime_requirements",
    ])
}

def get_std_ci_script(String std_ci_stage, String distro, String arch) {
    def possible_paths = [
        [std_ci_stage, distro, arch, 'sh'],
        [std_ci_stage, distro, 'sh'],
        [std_ci_stage, 'sh'],
    ].findResults { get_possible_file_paths(it) }
    for(pi = 0; pi < possible_paths.size(); ++pi) {
        def possible_path = possible_paths[pi].join('.')
        if(fileExists(possible_path)) {
            return possible_path
        }
    }
}

def get_std_ci_list(List<String> locations) {
    def rv = get_std_ci_object(locations)
    def o = rv.object
    def l = rv.location
    if(o == null) {
        return []
    } else if (o in Collection) {
        return o.collect { it as String } as Set
    } else {
        error("Invalid data at ${l}, should be a list")
    }
}

def get_std_ci_dict(List<String> locations) {
    def rv = get_std_ci_object(locations)
    def o = rv.object
    def l = rv.location
    if(o == null) {
        return [:]
    } else if(o in Map) {
        return o
    } else {
        error("Invalid data at ${l}, should be a mapping")
    }
}

def get_std_ci_object(List<String> locations) {
    for(li = 0; li < locations.size(); ++li) {
        def paths = get_paths_for_location(locations[li])
        for(pi = 0; pi < paths.size(); ++ pi) {
            def path = paths[pi]
            if(!fileExists(path.file_path)) {
                continue
            }
            def yaml = readYaml file: path.file_path
            def o = get_yaml_object(yaml, path.yaml_path)
            if(o == null) {
                continue
            }
            return [
                object: o,
                location: "${path.file_path}[${path.yaml_path}]"
            ]
        }
    }
    return [ object: null, location: "--not-found--", ]
}

@NonCPS
def get_paths_for_location(String location, List extentions=['yaml', 'yml']) {
    def parts = location.tokenize('.')
    if(parts.size() > 1) {
        return get_possible_file_paths(parts[0..-2], extentions).collect { pt ->
            return [ file_path: pt, yaml_path: parts[-1..-1], ]
        }
    } else {
        return extentions.collect { extention ->
            return [ file_path: "automation.$extention", yaml_path: parts, ]
        }
    }
}

@NonCPS
def get_possible_file_paths(List path_parts, List extentions = ['']) {
    extentions.collectMany { extention ->
        if(extention.empty) {
            [ "automation/${path_parts.join('.')}", ]
        } else {
            ((path_parts.size()-1)..0).collect { ext_pos ->
                'automation/' + (
                    path_parts[0..ext_pos] + [extention] +
                    path_parts[ext_pos+1..<path_parts.size()]
                ).join('.')
            }
        }
    }
}

@NonCPS
def get_yaml_object(Object yaml, List yaml_path) {
    yaml_path.inject(yaml) { yaml_ptr, path_part ->
        if(yaml_ptr in Map) {
            yaml_ptr.get(path_part)
        } else if(yaml_ptr in Collection) {
            yaml_ptr.findResult {
                if(it in Map) {
                    it.get(path_part)
                }
            }
        }
    }
}

def run_std_ci_jobs(project, jobs) {
    def branches = [:]
    for(job in jobs) {
        branches["${job.stage}.${job.distro}.${job.arch}"] = \
            mk_std_ci_runner(project, job)
    }
    parallel branches
}

def mk_std_ci_runner(project, job) {
    return {
        String ctx = "${job.stage}.${job.distro}.${job.arch}"
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
    return "${job.stage}.${job.distro}.${job.arch}"
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
    String ctx = "${job.stage}.${job.distro}.${job.arch}"
    try {
        try {
            project.notify(ctx, 'PENDING', 'Setting up test environment')
            dir("exported-artifacts") { deleteDir() }
            checkout_jenkins_repo()
            checkout_project(project)
            run_jjb_script('cleanup_slave.sh', project.name)
            run_jjb_script('global_setup.sh', project.name)
            run_std_ci_in_mock(project, job, tfr)
        } finally {
            project.notify(ctx, 'PENDING', 'Collecting results')
            dir("exported-artifacts") {
                stash includes: '**', name: stash_name
            }
        }
        // The only way we can get to these lines is if nothing threw any
        // exceptions so far. This means the job was successful.
        run_jjb_script('global_setup_apply.sh', project.name)
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

def run_jjb_script(script_name, project_name) {
    def script_path = "jenkins/jobs/confs/shell-scripts/$script_name"
    echo "Running JJB script: ${script_path}"
    def script = readFile(script_path)
    withEnv(["WORKSPACE=${pwd()}", "PROJECT=$project_name"]) {
        sh script
    }
}

def run_std_ci_in_mock(Project project, def job, TestFailedRef tfr) {
    String ctx = "${job.stage}.${job.distro}.${job.arch}"
    try {
        run_jjb_script('mock_setup.sh', project.name)
        // TODO: Load mirros once for whole pipeline
        // unstash 'mirrors'
        // def mirrors = "${pwd()}/mirrors.yaml"
        def mirrors = null
        dir(project.name) {
            project.notify(ctx, 'PENDING', 'Running test')
            // Set flag to 'true' to indicate that exception from this point
            // means the test failed and not the CI system
            tfr.test_failed = true
            mock_runner(job.script, job.distro, job.arch, mirrors)
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
            run_jjb_script('collect_artifacts.sh', project.name)
        }
        project.notify(ctx, 'PENDING', 'Cleaning up')
        run_jjb_script('mock_cleanup.sh', project.name)
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
