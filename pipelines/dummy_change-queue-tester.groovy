// dummy_change-queue-tester - Dummy change queue tests
//
import groovy.transform.Field

@Field def ost_project

def on_load(loader) {
    project_lib = loader.load_code('libs/stdci_project.groovy')

    run_jjb_script = loader.&run_jjb_script
    checkout_jenkins_repo = loader.&checkout_jenkins_repo
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
