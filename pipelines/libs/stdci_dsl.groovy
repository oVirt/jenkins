// stdci_dsl.groovy - Groovy wrapper for STDCI DSL parser
//

class JobProperties implements Serializable {
    def jobs
    def global_options
    Boolean is_gated_project

    @NonCPS
    def get_queues(String branch) {
        def o = this.global_options.release_branches.get(branch, [])
        if (o in Collection) {
            return o.collect { it as String } as Set
        } else {
            return [o as String]
        }
    }
}

def parse(String source_dir, String std_ci_stage) {
    def stdci_job_properties = "jobs_for_${std_ci_stage}.yaml"
    withEnv([
        'PYTHONPATH=jenkins',
        "POD_NAME_PREFIX=${env.JOB_BASE_NAME}-${env.BUILD_NUMBER}",
        "STD_CI_JOB_KEY=${env.BUILD_TAG}",
        "CI_SECURE_IMAGES=${env.CI_SECURE_IMAGES ?: 'quay.io/pod_utils/am_i'}",
    ]) {
        sh(
            label: 'Parsing STDCI DSL',
            script: """\
                #!/usr/bin/env python
                import yaml
                from scripts.stdci_dsl.api import (
                    get_formatted_threads, setupLogging
                )
                from scripts.zuul_helpers import is_gated_project

                setupLogging()
                stdci_config = get_formatted_threads(
                    'pipeline_dict', '${source_dir}', '${std_ci_stage}'
                )

                # Inject gating info into STDCI config
                stdci_config_parsed = yaml.safe_load(stdci_config)
                stdci_config_parsed['is_gated_project'] = \
                    is_gated_project('${source_dir}')
                stdci_config = yaml.safe_dump(
                    stdci_config_parsed, default_flow_style=False
                )

                with open('${stdci_job_properties}', 'w') as conf:
                    conf.write(stdci_config)
            """.stripIndent()
        )
    }
    def cfg = readYaml file: stdci_job_properties

    return new JobProperties(
        jobs: cfg.jobs,
        global_options: cfg.global_config,
        is_gated_project: cfg.is_gated_project,
    )
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
