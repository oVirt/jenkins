// ovirt_change-queue-tester - Change queue tests for oVirt
//
def project_lib

def ovirt_release
def ost_project


def on_load(loader) {
    // Copy methods from loader to this script
    metaClass.checkout_repo = {
        repo_name, refspec='refs/heads/master', url=null, head=null,
        clone_dir_name=null -> loader.metaClass.invokeMethod(
            loader, 'checkout_repo',
            [repo_name, refspec, url, head, clone_dir_name])
    }
    metaClass.checkout_jenkins_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_jenkins_repo', args)
    }
    metaClass.make_extra_sources = { ...args ->
        loader.metaClass.invokeMethod(loader, 'make_extra_sources', args)
    }
    metaClass.run_jjb_script = { ...args ->
        loader.metaClass.invokeMethod(loader, 'run_jjb_script', args)
    }

    ovirt_release = get_queue_ovirt_release()

    metaClass.load_code = { code_file, load_as=null ->
        loader.metaClass.invokeMethod(
            loader, 'load_code', [code_file, load_as])
    }
    project_lib = load_code('libs/stdci_project.groovy', this)
}

def extra_load_change_data_py(change_list_var, mirrors_var) {
    return """\
        from scripts.mirror_client import ovirt_tested_as_mirrors

        ${mirrors_var}.update(ovirt_tested_as_mirrors('${ovirt_release}'))
    """.stripIndent()
}

def wait_for_artifacts(change_data) {
    wait_for_tested_deployment(ovirt_release)
}

def run_tests(change_data) {
    run_ost_tests(change_data, ovirt_release)
}

def deploy(change_data) {
    deploy_to_tested(ovirt_release, change_data)
}

@NonCPS
def get_queue_ovirt_release() {
    def match = (env.JOB_NAME =~ /^ovirt-(.*)_change-queue-tester$/)
    if(match.asBoolean()) {
        return match[0][1]
    } else {
        error "Failed to detect oVirt release from job name"
    }
}

def run_ost_tests(change_data, ovirt_release) {
    ost_project = get_ost_project()
    def ost_suit_types = get_available_ost_suit_types(ovirt_release)
    echo "Will run the following OST ($ovirt_release) " +
        "suits: ${ost_suit_types.join(', ')}"
    def branches = [:]
    // Need to fallback to an empty string for mirrors to avoid edge case when
    // writing it to a file
    def mirrors = change_data.get('mirrors', '')
    for(suit_type in ost_suit_types) {
        branches["${suit_type}-suit"] = \
            mk_ost_runner(mirrors, ovirt_release, suit_type, 'el7')
    }
    parallel branches
}

def get_available_ost_suit_types(ovirt_release) {
    def suit_types_to_use = [
        'basic', 'upgrade-from-release', 'upgrade-from-prevrelease'
    ]
    def available_suits = []
    project_lib.checkout_project(ost_project)
    dir('ovirt-system-tests') {
        for(suit_type in suit_types_to_use) {
            if(fileExists("automation/${suit_type}_suite_${ovirt_release}.sh"))
                available_suits << suit_type
        }
    }
    return available_suits
}

def mk_ost_runner(mirrors, ovirt_release, suit_type, distro) {
    return {
        def suit_dir = "$suit_type-suit-$ovirt_release-$distro"
        // stash an empty file so we don`t get errors in no artifacts get stashed
        writeFile file: '__no_artifacts_stashed__', text: ''
        stash includes: '__no_artifacts_stashed__', name: suit_dir
        try {
            node('integ-tests') {
                run_ost_on_node(
                    mirrors, ovirt_release, suit_type, distro, suit_dir)
            }
        } finally {
            dir("exported-artifacts/$suit_dir") {
                unstash suit_dir
            }
        }
    }
}

def get_ost_project() {
    def base_scm_url = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
    return project_lib.new_project(
        clone_url: base_scm_url + '/ovirt-system-tests',
        name: 'ovirt-system-tests'
    )
}

def run_ost_on_node(mirrors, ovirt_release, suit_type, distro, stash_name) {
    checkout_jenkins_repo()
    project_lib.checkout_project(ost_project)
    run_jjb_script('cleanup_slave.sh')
    run_jjb_script('global_setup.sh')
    run_jjb_script('mock_setup.sh')
    try {
        def suit_path = "ovirt-system-tests/$suit_type-suite-$ovirt_release"
        def reposync_config = "*.repo"
        def mirrors_file = "${pwd()}/mirrors.yaml"
        writeFile file: mirrors_file, text: mirrors
        inject_mirrors(suit_path, reposync_config, mirrors_file)
        dir(suit_path) {
            stash includes: reposync_config, name: "$stash_name-injected"
        }
        dir('ovirt-system-tests') {
            unstash 'extra_sources'
            mock_runner(
                "${suit_type}_suite_${ovirt_release}.sh",
                distro,
                mirrors_file
            )
        }
    } finally {
        dir('ovirt-system-tests/exported-artifacts') {
            unstash "$stash_name-injected"
            stash includes: '**', name: stash_name
        }
        run_jjb_script('mock_cleanup.sh')
    }
    run_jjb_script('global_setup_apply.sh')
}

def inject_mirrors(path, file_pattern, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    withEnv(["PYTHONPATH=${pwd()}/jenkins"]) {
        dir(path) {
            sh """\
                #!/usr/bin/env python
                # Try to inject CI mirrors
                from scripts.mirror_client import (
                    inject_yum_mirrors_file_by_pattern,
                    mirrors_from_uri, setupLogging
                )

                setupLogging()
                inject_yum_mirrors_file_by_pattern(
                    mirrors_from_uri('$mirrors'),
                    '$file_pattern'
                )
            """.stripIndent()
        }
    }
}

def mock_runner(script, distro, mirrors=null) {
    if(mirrors == null) {
        mirrors = env.CI_MIRRORS_URL
    }
    mirrors_arg=''
    if(mirrors != null) {
        mirrors_arg = "--try-mirrors '$mirrors'"
    }
    sh """
        ../jenkins/mock_configs/mock_runner.sh \\
            --execute-script "automation/$script" \\
            --mock-confs-dir ../jenkins/mock_configs \\
            --try-proxy \\
            $mirrors_arg \
            "${distro}.*x86_64"
    """
}

def wait_for_tested_deployment(version) {
    def job_name = "deploy-to_ovirt-${version}_tested"
    def build_id
    def queue_id = get_queue_id(job_name)
    if(queue_id != null) {
        waitUntil {
            print("Waiting for queued ${job_name} to be start building")
            !is_in_queue(queue_id)
        }
        build_id = get_build_from_queue(job_name, queue_id)
        if(build_id == null) {
            print("${job_name} build was removed from queue")
            return
        }
    } else {
        build_id = get_last_build(job_name)
        if(build_id == null) {
            print("${job_name} seems to have never been built")
            return
        }
    }
    if(!build_is_done(job_name, build_id)) {
        waitUntil {
            print("${job_name} ($build_id} is still building")
            build_is_done(job_name, build_id)
        }
    }
}

def deploy_to_tested(version, change_data) {
    def extra_sources = make_extra_sources(change_data.builds)
    build(
        job: "deploy-to_ovirt-${version}_tested",
        parameters: [text(
            name: 'REPOMAN_SOURCES',
            value: extra_sources,
        )],
        wait: false,
    )
}

@NonCPS
def get_queue_id(job_name) {
    return Jenkins.instance.queue.items.toList().find({
        it.task.name == job_name
    })?.id
}

@NonCPS
def is_in_queue(queue_id) {
    Jenkins.instance.queue.getItem(queue_id) != null
}

@NonCPS
def get_build_from_queue(job_name, queue_id) {
    def job = Jenkins.instance.getItem(job_name)
    if(job == null) {
        print("Job: ${job_name} not found - ignoring")
        return null
    }
    return job.builds.find({ bld -> bld.queueId == queue_id })?.id
}

@NonCPS
def get_last_build(job_name) {
    def job = Jenkins.instance.getItem(job_name)
    if(job == null) {
        print("Job: ${job_name} not found - ignoring")
        return null
    }
    def builds = job.getNewBuilds()
    if(builds.isEmpty()) {
        return null
    } else {
        return builds.first().id
    }
}

@NonCPS
def build_is_done(job_name, build_id) {
    def job = Jenkins.instance.getItem(job_name)
    if(job == null) {
        print("Job: ${job_name} not found - ignoring")
        return true
    }
    def build = job.getBuild(build_id)
    if(build == null) {
        print("Cannot find build ${build_id} of ${job_name}.")
        return true
    }
    return !build.isBuilding()
}

// We need to return 'this' so the tester job can invoke functions from
// this script
return this
