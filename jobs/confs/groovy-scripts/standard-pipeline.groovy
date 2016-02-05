import jenkins.model.Jenkins

project='{project}'
branch='{branch}'
trigger_stage='{stage}'
job_prefix='http://jenkins.ovirt.org/job/'
with_build_and_deploy = false


if (trigger_stage == 'check-merged') {{
    with_build_and_deploy = true
}}


// This decorator allows using jenkins internal non-serializable objects
// see https://github.com/jenkinsci/workflow-plugin/blob/master/TUTORIAL.md
@NonCPS
def get_jobs(project, version, trigger_stage) {{
    def jobs = Jenkins.instance.items.findAll {{ job ->
        job.name =~ /^${{project}}_${{version}}_${{trigger_stage}}/ \
        && job.name != env.JOB_NAME \
        && ! job.name.endsWith('-trigger')
    }}.collect {{ job ->
        job.name
    }}
    return jobs
}}


def run_checks(project, branch, trigger_stage) {{
    // runs the check jobs
    stage concurrency: 5, name: 'Running checks'
    def check_jobs = get_jobs(project, branch, trigger_stage)
    println "Found ${{check_jobs.size()}} check jobs"
    def checkers = [:]
    for (int i = 0; i < check_jobs.size(); i++) {{
        def job_name = check_jobs[i]
        checkers[job_name] = {{
            build([
                job: job_name,
                parameters: [
                    [
                        $class: 'StringParameterValue',
                        name: 'GERRIT_REFSPEC',
                        value: env.GERRIT_REFSPEC?: ''
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'GERRIT_BRANCH',
                        value: env.GERRIT_BRANCH?: ''
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'REFSPEC',
                        value: env.REFSPEC?: ''
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'sha1',
                        value: env.sha1?: ''
                    ]
                ]
            ])
        }}
    }}
    return parallel(checkers)
}}


def build_artifacts(project, branch) {{
    // runs the build jobs
    stage concurrency: 5, name: 'Building'
    def build_jobs = get_jobs(project, branch, 'build-artifacts')
    println "Found ${{build_jobs.size()}} build jobs"
    def builders = [:]
    for (int i = 0; i < build_jobs.size(); i++) {{
        def job_name = build_jobs[i]
        builders[job_name] = {{
            build([
                job: job_name,
                parameters: [
                    [
                        $class: 'StringParameterValue',
                        name: 'GERRIT_REFSPEC',
                        value: env.GERRIT_REFSPEC?: ''
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'GERRIT_BRANCH',
                        value: env.GERRIT_BRANCH?: ''
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'REFSPEC',
                        value: env.REFSPEC?: ''
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'sha1',
                        value: env.sha1?: ''
                    ]

                ]
            ])
        }}
    }}
    return parallel(builders)
}}


@NonCPS
def extract_builders_list(build_results) {{
    // this is not serializable, thus it has to go in a nonCPS method
    // retrieve all the full urls of the builders, to pass to the deplayers
    def builders_list = []
    build_results.each {{ job ->
        builders_list.add(
            job.getValue().getAbsoluteUrl()
        )
    }}
    return builders_list
}}


// Make sure that the global vars we extract exist, as they are not in the env object
for(varname in ['GERRIT_REFSPEC', 'GERRIT_BRANCH', 'REFSPEC', 'sha1']){{
    println "Setting env variable $varname"
    if(binding.variables.containsKey(varname)) {{
        env."$varname" = binding.variables[varname]
    }} else {{
        env."$varname" = ''
    }}
}}


def deploy(build_results, project, branch) {{
    // Runs the deploy jobs with the build_results
    builders_list = extract_builders_list(build_results)
    stage concurrency: 1, name: 'Deploying to snapshot'
    def deploy_jobs = get_jobs(project, branch, 'deploy-to-.*-snapshot')
    println "Found ${{deploy_jobs.size()}} deploy jobs"
    def deployers = [:]
    for (int i = 0; i < deploy_jobs.size(); i++) {{
        def job_name = deploy_jobs[i]
        deployers[job_name] = {{
            build([
                job: job_name,
                parameters: [
                    [
                        $class: 'StringParameterValue',
                        name: 'BUILD_ARTIFACTS_JOBS',
                        value: builders_list.join(',')
                    ],
                    [
                        $class: 'StringParameterValue',
                        name: 'BUILD_ID',
                        value: "${{env.JOB_NAME}}-${{env.BUILD_NUMBER}}"
                    ]
                ]
            ])
        }}
    }}
    return parallel(deployers)
}}


def main() {{
    def check_results = run_checks(project, branch, trigger_stage)
    if (with_build_and_deploy) {{
        def build_results = build_artifacts(project, branch)
        def deploy_results = deploy(build_results, project, branch)
    }}
}}

// dummy useless main
main()
