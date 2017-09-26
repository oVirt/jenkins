// dummy_change-queue-tester - Dummy change queue tests
//
def on_load(loader) {
    // Copy methods from loader to this script
    metaClass.checkout_jenkins_repo = { ...args ->
        loader.metaClass.invokeMethod(loader, 'checkout_jenkins_repo', args)
    }
    metaClass.run_jjb_script = { ...args ->
        loader.metaClass.invokeMethod(loader, 'run_jjb_script', args)
    }
}

def run_tests(change_data) {
    print "Allocating node to ensure it works"
    node() {
        print "Cloning jenkins repo to verify checkout_jenkins_repo method"
        checkout_jenkins_repo()
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
