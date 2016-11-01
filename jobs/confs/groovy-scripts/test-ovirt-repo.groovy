// To be filled in by jenkins
def reponame = '{reponame}'
def repotype = '{repotype}'
def version = '{version}'
def chroot_distro = '{chroot_distro}'

// This might change to something more reasonable once we upgrade the
// credentials plugin to allow short names, something like
// {reponame}-{repotype}-prepare-test and {reponame}-{repotype}-ack-repo
def credentials_prepare_test = '31ac54cf-8cf0-474c-9c86-fd5eb36f761c'
def credentials_ack_repo = '7abaf08a-57a9-4975-b1ee-0f75ab2f5f57'

// other derived globals
def project = 'ovirt-system-tests'
def git_project = "git://gerrit.ovirt.org/${{project}}"
def git_jenkins = 'git://gerrit.ovirt.org/jenkins'
def distros = ["${{chroot_distro}}"]
def scripts = ["basic_suite_${{version}}.sh"]
def deploy_server_url = "deploy-${{reponame}}-${{repotype}}@resources.ovirt.org"
def test_repo_url = "http://plain.resources.ovirt.org/repos/${{reponame}}/${{repotype}}/${{version}}/latest.under_testing"


def run_script(script_path) {{
    println "Running script $script_path"
    def curdir = pwd()
    //pipeline plugin removes the WORKSPACE env var
    withEnv(["WORKSPACE=$curdir"]) {{
        sh """
            set -e
            chmod +x $script_path
            ./$script_path
        """
    }}
}}


def run_script_template(script_tpl_path, distro) {{
    def script_path = script_tpl_path.split('/')[-1]
    def curdir = pwd()
    println "Running template script $script_tpl_path"
    //pipeline plugin removes the WORKSPACE env var
    withEnv(["WORKSPACE=$curdir"]) {{
        sh """
            set -eo pipefail
            rm -f "$script_path"
            cat "$script_tpl_path" \\
            | python -c "
import sys
my_str=sys.stdin.read()
print my_str.format(distro='$distro')
" \\
            > "$script_path"
            chmod +x "$script_path"
            "./$script_path"
        """
    }}
}}


def prepare_export_artifacts(outdir) {{
    sh """
        mkdir -p "../$outdir"
        sudo chown -R "\$USER:\$USER" "../$outdir"
        if ls exported-artifacts/* &>/dev/null; then
            sudo mv exported-artifacts/* "../$outdir/"
            sudo rmdir exported-artifacts
        fi
    """
}}


def mock_runner(script, distro) {{
    sh """
        ../jenkins/mock_configs/mock_runner.sh \\
            --execute-script "automation/$script" \\
            --mock-confs-dir ../jenkins/mock_configs \\
            --try-proxy \\
            "${{distro}}.*x86_64"
    """
}}

def run_mock_script(
    distro,
    script,
    git_jenkins,
    project,
    git_project,
    outdir,
    repo_url
) {{
    try {{
        run_script('jenkins/jobs/confs/shell-scripts/cleanup_slave.sh')
        run_script('jenkins/jobs/confs/shell-scripts/global_setup.sh')
        run_script_template(
            'jenkins/jobs/confs/shell-scripts/mock_setup.sh',
            distro
        )
        dir(project) {{
            sh "git log -1"
            sh "echo rec:$repo_url > extra_sources"
            mock_runner(script, distro)
            prepare_export_artifacts(outdir)
        }}
        run_script('jenkins/jobs/confs/shell-scripts/mock_cleanup.sh')
    }} catch(err) {{
        println "ERROR:Got exception while running $script:"
        println err
        prepare_export_artifacts(outdir)
        run_script('jenkins/jobs/confs/shell-scripts/mock_cleanup.sh')
        throw err
    }}
}}


def checkout(project, git_project, git_jenkins) {{
    println "############################# Checking out the code"
    println "$project, $git_project, $git_jenkins"
    node ('fc23 || el7') {{
        wrap([$class: 'TimestamperBuildWrapper']) {{
            sh 'rm -rf ./*'
            dir(project) {{
                git url: git_project
            }}
            dir('jenkins') {{
                git url: git_jenkins
            }}
            //the last slash and the explicit .git are required
            sh "tar czf sources.tar.gz jenkins '$project'"
            stash includes: "sources.tar.gz", name: 'sources'
        }}
    }}
}}


def run_checks(
    scripts,
    distros,
    project,
    git_project,
    git_jenkins,
    extra_repo_url
) {{
    println "############################# Running checks"
    def branches = [:]
    for (int i = 0; i < scripts.size(); i++) {{
        for (int j = 0; j < distros.size(); j++) {{
            def script = "${{scripts[i]}}"
            def distro = "${{distros[j]}}"
            def my_project = "$project"
            branches["script_${{script}}_${{distro}}"] = {{
                node('integ-tests') {{
                    wrap([$class: 'TimestamperBuildWrapper']) {{
                        try {{
                               sh 'rm -rf ./*'
                               unstash 'sources'
                               sh 'tar xzf sources.tar.gz'
                               run_mock_script(
                                "$distro",
                                "$script",
                                "$git_jenkins",
                                "$my_project",
                                "$git_project",
                                "$script-$distro",
                                "$extra_repo_url",
                            )
                        }} catch(err) {{
                            println err
                            currentBuild.result = 'FAILURE'
                        }}
                        sh "mv ./exported-artifacts/ './$script-$distro'"
                        if(fileExists("./$my_project/exported-artifacts")) {{
                            sh "mv ./$my_project/exported-artifacts/ './$script-$distro/'"
                        }}
                        println "stashing $script-$distro"
                        stash includes: "$script-$distro/**,$script-$distro/*", name: "$script-$distro"
                    }}
                }}
            }}
        }}
    }}
    parallel branches
}}


def do_archive(scripts, distros) {{
    println "############################# Archiving"
    node {{
        wrap([$class: 'TimestamperBuildWrapper']) {{
            sh 'rm -rf *'
            sh 'mkdir exported-artifacts'
            for (int i = 0; i < scripts.size(); i++) {{
                for (int j = 0; j < distros.size(); j++) {{
                    def script = "${{scripts[i]}}"
                    def distro = "${{distros[j]}}"
                    dir('exported-artifacts') {{
                        println "unstashing $script-$distro"
                        unstash "$script-$distro"
                    }}
                }}
            }}
            archive 'exported-artifacts/**'
        }}
        try {{
            step([
                $class: 'JUnitResultArchiver',
                testResults: '**/*xml',
                allowEmptyResults: true
            ])
        }} catch(err) {{
            currentBuild.result = 'FAILURE'
            throw err
        }}
    }}
}}


def prepare_test_repo(deploy_server_url, version, credentials) {{
    node {{
        wrap([$class: 'TimestamperBuildWrapper']) {{
            sshagent([credentials]) {{
                sh "echo '${{version}}' | ssh -o StrictHostKeyChecking=no $deploy_server_url"
            }}
        }}
    }}
}}


def ack_test_repo(deploy_server_url, version, credentials) {{
    node {{
        wrap([$class: 'TimestamperBuildWrapper']) {{
            sshagent(['7abaf08a-57a9-4975-b1ee-0f75ab2f5f57']) {{
                sh "echo '${{version}}' | ssh -o StrictHostKeyChecking=no $deploy_server_url"
            }}
        }}
    }}
}}


def notify(PROJECT_NAME, BUILD_STATUS) {{
  // send to email
  node {{
      emailext (
          subject: """[oVirt Jenkins] ${{env.JOB_NAME}} - Build #${{env.BUILD_NUMBER}} - ${{BUILD_STATUS}}!""",
          body: """Build: ${{env.BUILD_URL}},
Build Number: ${{env.BUILD_NUMBER}},
Build Status: ${{BUILD_STATUS}}""",
          to: 'infra@ovirt.org',
          mimeType: 'text/plain'
    )
  }}
}}


def main(
    project,
    git_project,
    git_jenkins,
    distros,
    version,
    deploy_server_url,
    scripts,
    test_repo_url,
    credentials_prepare_test,
    credentials_ack_repo
) {{
    stage concurrency: 1, name: 'Testing latest repo'
    prepare_test_repo(deploy_server_url, version, credentials_prepare_test)
    checkout(
        project,
        git_project,
        git_jenkins,
    )
    run_checks(
        scripts,
        distros,
        project,
        git_project,
        git_jenkins,
        test_repo_url,
    )
    do_archive(scripts, distros)
    if (currentBuild.result != 'FAILURE') {{
        ack_test_repo(deploy_server_url, version, credentials_ack_repo)
        if (currentBuild.rawBuild.getPreviousCompletedBuild()?.getResult() == 'FAILURE') {{
            notify(project, 'SUCCESS')
        }}
    }} else {{
        println "Not promoting testing repo, as current build is '${{currentBuild.result}}'"
        notify(project, currentBuild.result)
    }}
}}


main(
    project,
    git_project,
    git_jenkins,
    distros,
    version,
    deploy_server_url,
    scripts,
    test_repo_url,
    credentials_prepare_test,
    credentials_ack_repo
)
