// dummy_change-queue-tester - Dummy change queue tests
//
def project_lib
def ost_project

def on_load(loader) {
    // Copy methods from loader to this script
    metaClass.checkout_jenkins_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_jenkins_repo', args)
    }
    metaClass.make_extra_sources = { ...args ->
        loader.metaClass.invokeMethod(loader, 'make_extra_sources', args)
    }
    metaClass.run_jjb_script = { ...args ->
        loader.metaClass.invokeMethod(loader, 'run_jjb_script', args)
    }
    metaClass.checkout_repo = {
        repo_name, refspec='refs/heads/master', url=null, head=null,
        clone_dir_name=null -> loader.metaClass.invokeMethod(
            loader, 'checkout_repo',
            [repo_name, refspec, url, head, clone_dir_name])
    }

    metaClass.load_code = { code_file, load_as=null ->
        loader.metaClass.invokeMethod(
            loader, 'load_code', [code_file, load_as])
    }
    project_lib = load_code('libs/stdci_project.groovy', this)
}

def get_ost_project() {
    // Needed only for testing OST on staging-jenkins.
    withEnv(['DEFAULT_SCM_URL_PREFIX=https://gerrit.ovirt.org']) {
        def base_scm_url = env.DEFAULT_SCM_URL_PREFIX ?: 'https://gerrit.ovirt.org'
        return project_lib.new_project(
            clone_url: base_scm_url + '/ovirt-system-tests',
            name: 'ovirt-system-tests'
        )
    }
}

def run_tests(change_data) {
    print "Allocating node to ensure it works"
    node() {
        print "Cloning jenkins repo to verify checkout_jenkins_repo method"
        checkout_jenkins_repo()
        print "Getting OST project to verify it works"
        ost_project = get_ost_project()
        print "Cloning OST repo to verify checkout_project method"
        project_lib.checkout_project(ost_project)
        print "Running node setup scripts to verify run_jjb_script method"
        run_jjb_script('cleanup_slave.sh')
        run_jjb_script('global_setup.sh')
        print "--- Actual tests in node go here ---"
        run_jjb_script('global_setup_apply.sh')
    }
    print "We don't have any real tests, so we'll just sleep"
    sleep time: 3, unit: 'MINUTES'
}

// We need to return 'this' so the tester job can invoke functions from
// this script
return this
