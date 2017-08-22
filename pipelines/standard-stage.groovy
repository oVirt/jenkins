// standard-stage.groovy - Pipeling-based STD-CI implementation
//
def loader_main(loader) {
    String std_ci_stage
    Project project
    def jobs
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
            def job_list = "Will run ${jobs.size} job(s):"
            job_list += jobs.collect { job ->
                "\n- ${job.stage}.${job.distro}.${job.arch}"
            }.join()
            print(job_list)
        }
    }
    try {
        stage('Invoking jobs') {
            run_std_ci_jobs(project, jobs)
        }
    } finally {
        stage('Collecting results') {
            archiveArtifacts allowEmptyArchive: true, \
                artifacts: 'exported-artifacts/**'
            junit keepLongStdio: true, allowEmptyResults: true, \
                testResults: 'exported-artifacts/**/*xml'
        }
    }
}

@NonCPS
def get_stage_name() {
    if('STD_CI_STAGE' in params) {
        return params.STD_CI_STAGE
    }
    error "Failed to detect stage from trigger event or parameters"
}

class Project implements Serializable {
    String clone_url
    String name
    String refspec
}

def get_project() {
    if('STD_CI_CLONE_URL' in params) {
        get_project_from_params()
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

def checkout_project(Project project) {
    checkout_repo(project.name, project.refspec, project.clone_url)
}

def get_std_ci_jobs(project, std_ci_stage) {
    checkout_project(project)
    dir(project.name) {
        def jobs = []
        def distros = get_std_ci_distros(std_ci_stage)
        for(di = 0; di < distros.size; ++di) {
            def distro = distros[di]
            def archs = get_std_ci_archs(std_ci_stage, distro)
            for(ai = 0; ai < archs.size; ++ai) {
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
        "${distro}.archs",
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
        "${distro}.runtime_requirements",
        "${arch}.runtime_requirements",
        "runtime_requirements",
    ])
}

def get_std_ci_script(String std_ci_stage, String distro, String arch) {
    def possible_paths = [
        [std_ci_stage, distro, arch, 'sh'],
        [std_ci_stage, distro, 'sh'],
        [std_ci_stage, 'sh'],
    ].findResults { get_possible_file_paths(it) }
    for(pi = 0; pi < possible_paths.size; ++pi) {
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
    for(li = 0; li < locations.size; ++li) {
        def paths = get_paths_for_location(locations[li])
        for(pi = 0; pi < paths.size; ++ pi) {
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
    (parts.size>1 ? [parts.size, parts.size-1] : [1]).collectMany { path_end ->
        get_possible_file_paths(parts[0..<path_end], extentions).collect { pt ->
            return [
                file_path: pt,
                yaml_path: parts[path_end..<parts.size],
            ]
        }
    }
}

@NonCPS
def get_possible_file_paths(List path_parts, List extentions = ['']) {
    extentions.collectMany { extention ->
        if(extention.empty) {
            [ "automation/${path_parts.join('.')}", ]
        } else {
            ((path_parts.size-1)..0).collect { ext_pos ->
                'automation/' + (
                    path_parts[0..ext_pos] + [extention] +
                    path_parts[ext_pos+1..<path_parts.size]
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
        def job_dir = "${job.stage}.${job.distro}.${job.arch}"
        // stash an empty file so we don`t get errors if no artifacts get stashed
        touch file: '__no_artifacts_stashed__'
        stash includes: '__no_artifacts_stashed__', name: job_dir
        try {
            String node_label = get_std_ci_node_label(job)
            if(node_label.empty) {
                print "This script has no special node requirements"
            } else {
                print "This script required nodes with label: $node_label"
            }
            node(node_label) {
                run_std_ci_on_node(project, job, job_dir)
            }
        } finally {
            dir("exported-artifacts/$job_dir") {
                unstash job_dir
            }
        }
    }
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

def run_std_ci_on_node(project, job, stash_name) {
    checkout_jenkins_repo()
    checkout_project(project)
    run_jjb_script('cleanup_slave.sh', project.name)
    run_jjb_script('global_setup.sh', project.name)
    try {
        run_jjb_script('mock_setup.sh', project.name)
        // TODO: Load mirros once for whole pipeline
        // unstash 'mirrors'
        // def mirrors = "${pwd()}/mirrors.yaml"
        def mirrors = null
        dir(project.name) {
            mock_runner(job.script, job.distro, job.arch, mirrors)
        }
    } finally {
        withCredentials([usernamePassword(
            credentialsId: 'ci-containers_intermediate-repository',
            passwordVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_PASSWORD',
            usernameVariable: 'CI_CONTAINERS_INTERMEDIATE_REPO_USERNAME'
        )]) {
            run_jjb_script('collect_artifacts.sh', project.name)
        }
        dir("exported-artifacts") {
            stash includes: '**', name: stash_name
        }
        run_jjb_script('mock_cleanup.sh', project.name)
    }
    run_jjb_script('global_setup_apply.sh', project.name)
}

def run_jjb_script(script_name, project_name) {
    def script_path = "jenkins/jobs/confs/shell-scripts/$script_name"
    echo "Running JJB script: ${script_path}"
    def script = readFile(script_path)
    withEnv(["WORKSPACE=${pwd()}", "PROJECT=$project_name"]) {
        sh script
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

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
