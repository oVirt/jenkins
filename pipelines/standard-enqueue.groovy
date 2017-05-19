// standard-enqueue.groovy - Jenkins pipeline script for submitting changes to
//                           change queues
//
import groovy.json.JsonOutput

def main() {
    def siblings
    def queues

    try {
        if(params.GERRIT_PROJECT) {
            currentBuild.displayName += " [${params.GERRIT_PROJECT}]"
        }
        stage('Sleep for siblings') {
            echo "Sleeping a while to let sibling jobs get invoked"
            sleep 5
        }
        stage('Build job search') {
            siblings = find_sibling_builds(/_build-artifacts-/)
            if(siblings.size() > 0) {
                echo "Found sibling builds:\n${buildsToStr(siblings)}"
                def projects_and_versions =
                    builds_projecs_and_versions(siblings)
                currentBuild.displayName =
                    "${currentBuild.id} ${pnv2str(projects_and_versions)}"
                queues = versions_to_queues(get_versions(projects_and_versions))
            } else {
                echo 'Did not find any sibling builds'
                currentBuild.result = 'NOT_BUILT'
            }
        }
        if(siblings.size() <= 0) {
            return
        }
        stage('Enqueue change') {
            withEnv(["BUILDS_LIST=${JsonOutput.toJson(siblings)}"]) {
                echo "Will enqueue to: ${queues.join(' ')}"
                enqueue_change_to(queues)
            }
        }
    } catch(Exception e) {
        // email_notify('FAILURE')
        throw(e)
    }
}

@NonCPS
def buildsToStr(builds) {
    return builds.findResults({
        if('build_id' in it) {
            "- job: ${it.job_name} build: ${it.build_id} (${it.build_url})"
        } else {
            "- job: ${it.job_name} (queued id: ${it.queue_id})"
        }
    }).join("\n")
}

def find_sibling_builds(job_pattern = /.*/) {
    if(params.containsKey('GERRIT_NAME') && params.containsKey('GERRIT_EVENT_HASH')) {
        print('I was invoked by a gerrit event')
        return find_gerrit_sibling_builds(job_pattern)
    } else {
        print('Cannot recognise the event I was invoked by to find siblings')
        return []
    }
}

@NonCPS
def find_gerrit_sibling_builds(job_pattern = /.*/) {
    find_gerrit_sibling_queued_builds(job_pattern) +
    find_gerrit_sibling_schedualed_builds(job_pattern)
}

@NonCPS
def find_gerrit_sibling_queued_builds(job_pattern = /.*/) {
    return jenkins.model.Jenkins.instance.queue.items.toList().findResults {
        if(it.task == currentBuild.rawBuild.parent) {
            // skip builds of this job
            return
        }
        if(!(it.task.name =~ job_pattern)) {
            // skip jobs that do not match given pattern
            return
        }
        def build_params = it.getAction(hudson.model.ParametersAction)
        if(!build_params) {
            return
        }
        if(
            build_params.getParameter('GERRIT_NAME')?.value == params['GERRIT_NAME'] &&
            build_params.getParameter('GERRIT_EVENT_HASH')?.value == params['GERRIT_EVENT_HASH']
        ) {
            return [
                job_name: it.task.name,
                job_url: it.task.url,
                queue_id: it.id,
            ]
        }
    }
}

@NonCPS
def find_gerrit_sibling_schedualed_builds(job_pattern = /.*/) {
    return jenkins.model.Jenkins.instance.allItems(
        hudson.model.Job
    ).findResults { job ->
        if(job == currentBuild.rawBuild.parent) {
            // skip builds of this job
            return
        }
        if(!(job.name =~ job_pattern)) {
            // skip jobs that do not match given pattern
            return
        }
        // We assume sibling builds are scheduled between 10 hours before to 30
        // minutes after this build. It is necessary to limit the search
        // because searching all builds will be far too slow
        return job.builds.byTimestamp(
            currentBuild.timeInMillis - 10 * 60 * 60 * 1000,
            currentBuild.timeInMillis + 30 * 60 * 1000
        ).findResult { build ->
            def build_params = build.getAction(hudson.model.ParametersAction)
            if(!build_params) {
                return
            }
            if(
                build_params.getParameter('GERRIT_NAME')?.value == params['GERRIT_NAME'] &&
                build_params.getParameter('GERRIT_EVENT_HASH')?.value == params['GERRIT_EVENT_HASH']
            ) {
                return [
                    job_name: job.name,
                    job_url: job.url,
                    build_id: build.id,
                    build_url: build.url
                ]
            }
        }
    }
}

@NonCPS
def builds_projecs_and_versions(builds) {
    builds.groupBy({ build_project_and_version(it)[0] }).collectEntries(
        { [it.key, it.value.groupBy({ build_project_and_version(it)[1] })] }
    )
}

@NonCPS
def build_project_and_version(build) {
    def match = (build.job_name =~ /(.*)_(.*)_build-artifacts.*/)
    if(match.asBoolean()) {
        return [match[0][1], match[0][2]]
    }
}

@NonCPS
def pnv2str(projects_and_versions) {
    projects_and_versions.collect({ project, versions ->
        "$project (${versions.collect({ it.key }).join(', ')})"
    }).join(', ')
}

@NonCPS
def get_versions(projects_and_versions) {
    projects_and_versions.collectMany([] as Set) { it.value.keySet() }
}

@NonCPS
def versions_to_queues(versions) {
    versions.collect { "ovirt-${it}" }
}

def email_notify(status, recipients='infra@ovirt.org') {
    emailext(
        subject: "[oVirt Jenkins] ${env.JOB_NAME}" +
            " - Build #${env.BUILD_NUMBER} - ${status}!",
        body: [
            "Build: ${env.BUILD_URL}",
            "Build Name: ${currentBuild.displayName}",
            "Build Status: ${status}",
            "Gerrit change: ${params.GERRIT_CHANGE_URL}",
            "- title: ${params.GERRIT_CHANGE_SUBJECT}",
            "- project: ${params.GERRIT_PROJECT}",
            "- branch: ${params.GERRIT_BRANCH}",
            "- author: ${params.GERRIT_CHANGE_OWNER_NAME}" +
            " <${params.GERRIT_CHANGE_OWNER_EMAIL}>",
        ].join("\n"),
        to: recipients,
        mimeType: 'text/plain'
    )
}

def enqueue_change_to(queues) {
    prepare_python_env()
    def enqueue_steps = [:]
    for(int i = 0; i < queues.size(); ++i) {
        def queue = queues[i]
        enqueue_steps[queue] = get_queue_build_step(queue)
    }
    parallel enqueue_steps
}

def get_queue_build_step(queue) {
    return {
        def build_args = get_queue_build_args(queue)
        build build_args
    }
}

def get_queue_build_args(queue) {
    def json_file = "${queue}_build_args.json"
    withEnv(['PYTHONPATH=jenkins']) {
        sh """\
            #!/usr/bin/env python
            from scripts.change_queue import JenkinsChangeQueueClient
            from scripts.change_queue.changes import GerritMergedChange

            jcqc = JenkinsChangeQueueClient('${queue}')
            change = GerritMergedChange.from_jenkins_env()
            jcqc.add(change).as_pipeline_build_step_json('${json_file}')
        """.stripIndent()
    }
    def build_args = readJSON(file: json_file)
    build_args['wait'] = true
    return build_args
}

def prepare_python_env() {
    sh """\
        #!/bin/bash -xe
        if [[ -e '/usr/bin/dnf' ]]; then
            sudo dnf install -y python-jinja2 python-paramiko
        else
            sudo yum install -y python-jinja2 python-paramiko
        fi
    """.stripIndent()
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
