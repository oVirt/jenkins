// standard-stage.groovy - Pipeling-based STD-CI implementation
//

import hudson.model.ParametersAction
import org.jenkinsci.plugins.workflow.support.steps.build.RunWrapper
import groovy.transform.Field

@Field def loader_node

def on_load(loader){
    project_lib = loader.load_code('libs/stdci_project.groovy')
    stdci_runner_lib = loader.load_code('libs/stdci_runner.groovy')
    dsl_lib = loader.load_code('libs/stdci_dsl.groovy')
    def build_params_lib = loader.load_code('libs/build_params.groovy')

    loader_node = loader.&loader_node
    modify_build_parameter = build_params_lib.&modify_build_parameter
}

@Field String std_ci_stage
@Field def project
@Field def jobs
@Field def queues
@Field def previous_build
@Field Boolean wait_for_previous_build
@Field Boolean call_beaker = false
@Field def rhel8_hosts
@Field def beaker_hosts
@Field def el8_hosts

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
        job_properties = dsl_lib.parse(project.clone_dir_name, std_ci_stage)
        jobs = job_properties.jobs
        queues = get_std_ci_queues(project, job_properties)
        save_gate_info(job_properties.is_gated_project, queues)
        if(!queues.empty && std_ci_stage != 'build-artifacts') {
            // If we need to submit the change the queues, make sure we
            // generate builds
            def build_job_properties = dsl_lib.parse(
                project.clone_dir_name, 'build-artifacts'
            )
            jobs += build_job_properties.jobs
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
            if(env.RUNNING_IN_PSI?.toBoolean()) {
                rhel8_hosts = 0
                el8_hosts = 0
                for(job in jobs) {
                    String node_label = stdci_runner_lib.get_std_ci_node_label(project, job)
                    if(node_label.contains("integ-tests")) {
                        call_beaker = true
                        // Counting the number of hosts needed by the jobs.
                        if(job.distro.equals("el8")) {
                            println(job.distro)
                            el8_hosts+=1
                        } else {
                            rhel8_hosts+=1
                        }

                    }
                }
            }
        }
    }
    if(call_beaker?.toBoolean()) {
        stage('Invoking beaker hosts') {
            invoke_beaker(rhel8_hosts, el8_hosts)
            for(host in beaker_hosts) {
                for(job in jobs) {
                    String node_label = stdci_runner_lib.get_std_ci_node_label(project, job)
                    if(node_label.contains("integ-tests") && job?.beaker_label == null) {
                        println(host.getClass())
                        if(host.split(':')[1].equals(job.distro)) {
                            job.beaker_label = host.split(':')[0]
                            break
                        }
                    }
                }
            }
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
    // If any of the threads use containers, we need to keep the loader node,
    // so we call main() from here instead of letting pipeline_loader call it
    // after releasing the node
    if(jobs.podspecs.any()) {
        return main()
    }
}

@Field Boolean main_done_already = false

def main() {
    // Allow skipping main() if it was already called once
    if(main_done_already) { return }
    main_done_already = true
    if(std_ci_stage == 'build-artifacts') {
        stage('Downloading existing build') {
            if(previous_build != null) {
                if(wait_for_previous_build) {
                    waitUntil {
                        echo "Waiting for build ${previous_build.number} to finish"
                        return previous_build.result != null
                    }
                    loader_node() {
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
    try {
        stage('Invoking jobs') {
            stdci_runner_lib.run_std_ci_jobs(project, jobs)
        }
    }
    finally {
        if(call_beaker?.toBoolean()) {
            stage('Removing beaker hosts from jenkins') {
                node('master') {
                    hudson.model.Hudson.instance.slaves.each {
                        for(host in beaker_hosts) {
                            if(it.name.contains(host.split(':')[0])) {
                                println "Deleting ${it.name}"
                                it.getComputer().doDoDelete()
                            }
                        }
                    }
                }
            }
        }
            // copy el8 jenkins artifacts from psi to us
        stage('Copying artifacts to us') {
            node('master') {
                println("Jenkins parameters:")
                println("Jenkins BUILD_NUMBER: ${env.BUILD_NUMBER}")
                println("Jenkins JOB_BASE_NAME: ${env.JOB_BASE_NAME}")
                println("Jenkins JOB_NAME: ${env.JOB_NAME}")
                println("Gerrit GERRIT_PATCHSET_NUMBER: ${env.GERRIT_PATCHSET_NUMBER}")
                println("Gerrit GERRIT_CHANGE_NUMBER: ${env.GERRIT_CHANGE_NUMBER}")
                println("Gerrit GERRIT_PATCHSET_REVISION: ${env.GERRIT_PATCHSET_REVISION}")
                if (env.RUNNING_IN_PSI?.toBoolean()) {
                    script: sh """#!/bin/bash -x
                            ci_copied_data_flag=0
                            job_dir_created=0
                            ci_log_user="ci-logs"
                            ci_log_host="buildlogs.ovirt.org"
                            ci_log_path="/var/www/html/ci-logs/jobs/\${JOB_NAME}/builds/\${BUILD_NUMBER}/archive"
                            ci_jenkins_path="/var/lib/jenkins/jobs/\${JOB_NAME}/builds/\${BUILD_NUMBER}/archive"
                            cd "\${ci_jenkins_path}"
                            if [[ \${JOB_NAME} =~ "ovirt-system-tests" ]]; then
                                for platform in */; do
                                    platform="\${platform%/*}"
                                    if [[ \$platform =~ ".el8.x86_64" ]]; then
                                        if [[ \$job_dir_created == 0 ]]; then
                                            ssh "\${ci_log_user}@\${ci_log_host}" "mkdir -p \${ci_log_path}"
                                            job_dir_created=1
                                        fi
                                        echo "PLATFORM: \$platform"
                                        echo "Starting copying data"
                                        scp -r "\${ci_jenkins_path}/\${platform}" "\${ci_log_user}@\${ci_log_host}:\${ci_log_path}"
                                        ssh "\${ci_log_user}@\${ci_log_host}" "chmod -R a+r \${ci_log_path}"
                                        echo "Finished copying data"
                                        ci_copied_data_flag=1
                                    fi
                                done
                                if [[ \$job_dir_created == 1 ]]; then
                                    ssh -p 29418 jenkins-psi2@gerrit.ovirt.org gerrit review \${GERRIT_CHANGE_NUMBER},\${GERRIT_PATCHSET_NUMBER} --message "http://\${ci_log_host}/ci-logs/jobs/\${JOB_NAME}/builds/\${BUILD_NUMBER}"
                                fi
                            fi
                    """
                }
            }
        }
    }
    if(!queues.empty && job_properties.is_gated_project) {
        stage('Deploying to gated repo') {
            deploy_to_gated(project, queues)
        }
    }
    println("call_beaker is set to: ${call_beaker}")
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

def get_std_ci_queues(project, job_properties) {
    if(get_stage_name() != 'check-merged') {
        // Only Enqueue on actual merge/push events
        return []
    }
    print "Checking if change should be enqueued"
    return job_properties.get_queues(project.branch)
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
    echo "Check Getting artifacts from previous build instead of building"
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

def invoke_beaker(rhel8_hosts, el8_hosts) {
    withCredentials(
        [
            usernamePassword(credentialsId: 'jenkins_user', usernameVariable: 'JENKINS_USERNAME', passwordVariable: 'JENKINS_PASSWORD'),
            file(credentialsId: 'keytab_file_creds', variable: 'STDCI_DS_KEYTAB'),
            string(credentialsId: 'keytab-username', variable: 'STDCI_DS_USERNAME'),
            file(credentialsId: 'redhat_internal_ca', variable: 'STDCI_DS_CA_FILE'),
            file(credentialsId: 'beaker_client', variable: 'BEAKER_CONF'),
            string(credentialsId: 'beaker_url', variable: 'BEAKER_URL'),
            file(credentialsId: 'beaker_repos', variable:  'BEAKER_REPOS')
        ]
    ){
        sh(
            label: 'Configuring worker for beaker',
            returnStdout: true,
            script: """
                cat <<EOF > /tmp/yum.conf
                [beaker-client]
                name=Beaker Client - CentOS\$releasever
                baseurl=https://beaker-project.org/yum/client/CentOS7/
                enabled=1
                gpgcheck=0
                EOF
                repo="\$(cat /tmp/yum.conf)"
                echo "\${repo}" | sudo -n tee -a /etc/yum.conf
                sudo -n yum install -y -q krb5-workstation beaker-client git jq python-lxml 1>&2
                sudo cp "\$STDCI_DS_CA_FILE" "\$BEAKER_CONF" /etc/beaker/.
                sudo -n chown "\$USER":"\$USER" /etc/beaker/*
            """.stripIndent()
        )
        def krbccname=sh(
            label: 'Login with Kerberos and installing beaker',
            returnStdout: true,
            script: """
                KRB5CCNAME="\$(mktemp \$WORKSPACE/.krbcc.XXXXXX)"
                REAL_KEYTAB="\$WORKSPACE/krb5.keytab"
                touch \$REAL_KEYTAB
                chmod 600 "\$REAL_KEYTAB"
                chmod 600 "\$KRB5CCNAME"
                /usr/bin/base64 -d "\$STDCI_DS_KEYTAB" > "\$REAL_KEYTAB"
                /usr/bin/kinit "\$STDCI_DS_USERNAME" -k -t "\$REAL_KEYTAB"
                sudo -n shred -u "\$STDCI_DS_KEYTAB" "\$REAL_KEYTAB"
                echo -n "\$KRB5CCNAME"
            """.stripIndent()
        )
        withEnv([
            "RHEL8_HOSTS_COUNTER=$rhel8_hosts",
            "EL8_HOSTS_COUNTER=$el8_hosts"
        ]) {
            sh(
                script: """
                    python "$WORKSPACE"/jenkins/stdci_libs/inject_repos.py \
                    -f "${BEAKER_REPOS}" \
                    -b "$WORKSPACE"/jenkins/data/slave-repos/beaker-rhel8.xml
                """.stripIndent()
            )
            String jenkins_url = env.JENKINS_URL.substring(0, env.JENKINS_URL.length() - 1)
            beaker_hosts=sh(
                label: 'Invoking beaker system to reserve a server',
                returnStdout: true,
                script: """
                    beaker_url=\$BEAKER_URL
                    for bkr_file in jenkins/data/slave-repos/beaker*.xml; do
                        sed -i "s/JENKINS-USER/${JENKINS_USERNAME}/" \$bkr_file
                        sed -i "s/JENKINS-PASS/${JENKINS_PASSWORD}/" \$bkr_file
                        sed -i "s#JENKINS-URL#${jenkins_url}#" \$bkr_file
                    done
                    beaker_hosts=()
                    for i in `seq 1 \$RHEL8_HOSTS_COUNTER`; do
                        job_number=\$(bkr job-submit jenkins/data/slave-repos/beaker-rhel8.xml | tr -dc '0-9')
                        host=\$(curl -k \$beaker_url/\$job_number -H "Accept: application/json" | jq .recipesets[0].machine_recipes[0].resource.fqdn)
                        while [[ ! \$host =~ "bkr" ]]; do
                            sleep 60
                            host=\$(curl -k \$beaker_url/\$job_number -H "Accept: application/json" | jq .recipesets[0].machine_recipes[0].resource.fqdn)
                        done
                        host=\${host%%.*}
                        beaker_hosts+=(\$host:rhel8)
                    done
                    for i in `seq 1 \$EL8_HOSTS_COUNTER`; do
                        job_number=\$(bkr job-submit jenkins/data/slave-repos/beaker-el8.xml | tr -dc '0-9')
                        host=\$(curl -k \$beaker_url/\$job_number -H "Accept: application/json" | jq .recipesets[0].machine_recipes[0].resource.fqdn)
                        while [[ ! \$host =~ "bkr" ]]; do
                            sleep 60
                            host=\$(curl -k \$beaker_url/\$job_number -H "Accept: application/json" | jq .recipesets[0].machine_recipes[0].resource.fqdn)
                        done
                        host=\${host%%.*}
                        beaker_hosts+=(\$host:el8)
                    done
                    echo -n \${beaker_hosts[@]}
                """.stripIndent()
            )
            beaker_hosts = beaker_hosts.replace("\"", "").tokenize()
            println(beaker_hosts)
        }
        withEnv(["KRB5CCNAME=$krbccname"]) {
            sh(
                label: 'Logout from Kerberos',
                script: "kdestroy"
            )
        }
    }
}
// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
