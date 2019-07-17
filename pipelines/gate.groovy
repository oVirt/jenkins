// gate.groovy - System pathc gating job

def project

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
    hook_caller = loader.load_code('libs/stdci_hook_caller.groovy', this)
    hook_caller = loader.hook_caller
    project_lib = loader.load_code('libs/stdci_project.groovy', this)
    stdci_runner_lib = loader.load_code('libs/stdci_runner.groovy', this)
}

def loader_main(loader) {
    stage('Analyzing patches') {
        // Global Var.
        build_thread_params = get_build_thread_parameters()
        def build_list = "Will run ${build_thread_params.size()} build(s):"
        build_list += build_thread_params.collect { "\n- ${it[2]}" }.join()
        print(build_list)
    }
}

def main() {
    stage('Building packages') {
        def threads = [:]
        releases_to_test = [:]
        threads = create_build_threads(build_thread_params, releases_to_test)
        parallel threads
    }
    stage('Running test suits') {
        def releases_list = "Will test the following releases and builds:"
        releases_list += releases_to_test.collect { release, builds ->
            def builds_list = builds.collect { "\n  - ${it}" }.join()
            "\n- ${release}:${builds_list}"
        }.join()
        print(releases_list)
    }
}

def create_build_threads(build_thread_params, releases_to_test) {
    def threads = [:]
    for (i = 0; i < build_thread_params.size(); ++i) {
        // build_thread_params have 3 elements inside the list by order of: job
        // run specs for jenkins, ovirt-releases and unique job name to display
        def job_run_spec = build_thread_params[i][0]
        def releases = build_thread_params[i][1]
        def thread_name = build_thread_params[i][2]
        threads[thread_name] = create_build_thread(
            job_run_spec, releases, releases_to_test
        )
    }
    return threads
}

def create_build_thread(job_run_spec, releases, releases_to_test) {
    return {
        job_run_spec['wait'] = true
        build_results = build(job_run_spec)
        releases.each { release ->
            def temp_url = releases_to_test.get(release, [])
            temp_url << build_results.absoluteUrl
            releases_to_test[release] = temp_url
        }
    }
}

def get_build_thread_parameters() {
    def build_thread_params = "build_thread_params_for_gating.json"
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            import json
            from os import environ
            from scripts.ost_build_resolver import create_patch_threads
            jobs = create_patch_threads(environ['CHECKED_COMMITS'])

            with open('${build_thread_params}', 'w') as jtb:
                json.dump(jobs, jtb)
        """.stripIndent()
    }
    def jobs = readJSON file: build_thread_params
    return jobs
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
