import jenkins.model.Jenkins

// substituted by JJB
main('{project}', '{branch}', '{stage}')

def main(project, branch, trigger_stage) {{
    stage("Asserting input") {{
        def result = check_empty_params(['sha1', 'REFSPEC'])
        result && error(result)
    }}
    stage(trigger_stage) {{
        run_standard_ci_stage(project, branch, trigger_stage)
    }}
    if (trigger_stage == 'check-merged') {{
        def build_results = null
        stage('build-artifacts') {{
            build_results = run_standard_ci_stage(project, branch,
                                                  'build-artifacts')
        }}
        milestone()
        def deploy_params = get_deploy_params(build_results)
        stage('deploy-to-.*-snapshot') {{
            run_standard_ci_stage(project, branch, 'deploy-to-.*-snapshot',
                                  deploy_params)
        }}
    }}
}}


@NonCPS
def get_jobs_names(project, version, trigger) {{
    def pattern = ~/^${{project}}_${{version}}_${{trigger}}/
    if (env.JOB_NAME == "${{project}}_${{version}}_github_check-merged-pipeline" ) {{
        pattern = ~/^${{project}}_${{version}}_github_${{trigger}}/
    }}
    def jobs_names = Jenkins.instance.items.findAll {{ job ->
        job.name =~ pattern \
        && job.name != env.JOB_NAME \
        && ! job.name.endsWith('-trigger')
    }}.collect {{ job ->
        job.name
    }}
    return jobs_names
}}

def create_jobs(jobs_names, job_params) {{
    def jobs = [:]
    for (int i = 0; i < jobs_names.size(); i++) {{
        // it is required to define 'job_name' in each iteration
        // so it will be in the scope of the closure.
        def job_name = jobs_names[i]
        jobs[job_name] = {{ build( [job: job_name, parameters: job_params]) }}
    }}
    return jobs
}}


def get_jobs(project, version, trigger_stage, job_params) {{
   def names = get_jobs_names(project, version, trigger_stage)
   return create_jobs(names, job_params)
}}

@NonCPS
def get_deploy_params(build_results) {{
    def build_urls = build_results.collect {{
            it.getValue().getAbsoluteUrl()
        }}.join(',')
    return [ string(name: 'BUILD_ARTIFACTS_JOBS', value: build_urls),
             string(name: 'BUILD_ID',
                    value: "${{env.JOB_NAME}}-${{env.BUILD_NUMBER}}") ]
}}

def get_common_params() {{
    return [ string(name: 'GERRIT_REFSPEC', value: params.GERRIT_REFSPEC?: ''),
             string(name: 'GERRIT_BRANCH', value: params.GERRIT_BRANCH?: ''),
             string(name: 'REFSPEC', value: params.REFSPEC),
             string(name: 'sha1', value: params.sha1) ]
}}


def run_standard_ci_stage(project, version, trigger, job_params=null) {{
    if (job_params == null) {{
        job_params = get_common_params()
    }}
    def jobs = get_jobs(project, version, trigger, job_params)
    if (jobs.size() < 1) {{
        error ("Unable to find any jobs for project: $project," +
                "version: $version, trigger: $trigger")
    }}
    return parallel(jobs)
}}

@NonCPS
def check_empty_params(vars) {{
    return vars.findAll {{
            params[it] == null || params[it].allWhitespace
        }}.collect {{
            "Missing parameter: $it"
        }}.join('\n')
}}
