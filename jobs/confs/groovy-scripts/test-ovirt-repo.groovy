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
def suits = ["basic","upgrade-from-release","upgrade-from-prevrelease"]
def deploy_server_url = "deploy-${{reponame}}-${{repotype}}@resources.ovirt.org"
def test_repo_url = "http://plain.resources.ovirt.org/repos/${{reponame}}/${{repotype}}/${{version}}/latest.under_testing"
ArrayList suites_to_run = [] as String[]

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


def mock_runner(script, distro) {{
    ansiColor('xterm') {{
        sh """
            try_mirrors=(\${{CI_MIRRORS_URL:+--try-mirrors "\$CI_MIRRORS_URL"}})

            ../jenkins/mock_configs/mock_runner.sh \\
                --execute-script "automation/$script" \\
                --mock-confs-dir ../jenkins/mock_configs \\
                --try-proxy \\
                "\${{try_mirrors[@]}}" \
                "${{distro}}.*x86_64"
        """
    }}
}}

def run_mock_script(
    version,
    suit,
    distro,
    git_jenkins,
    project,
    git_project,
    repo_url
) {{
    def reposync_config = "$suit-suite-$version/*.repo"
    def extra_sources = 'extra_sources'
    try {{
        run_script('jenkins/jobs/confs/shell-scripts/cleanup_slave.sh')
        run_script('jenkins/jobs/confs/shell-scripts/global_setup.sh')
        run_script_template(
            'jenkins/jobs/confs/shell-scripts/mock_setup.sh',
            distro
        )
        dir(project) {{
            sh "git log -1"
            withEnv(['PYTHONPATH=../jenkins']) {{
                sh """\
                    #!/usr/bin/env python
                    # Try to inject CI mirrors
                    from scripts.mirror_client import (
                        inject_yum_mirrors_file_by_pattern,
                        mirrors_from_environ, setupLogging
                    )

                    setupLogging()
                    inject_yum_mirrors_file_by_pattern(
                        mirrors_from_environ('CI_MIRRORS_URL'),
                        '$reposync_config'
                    )
                """.stripIndent()
            }}
            sh "echo rec:$repo_url/rpm/$distro > '$extra_sources'"
            mock_runner("${{suit}}_suite_${{version}}.sh", distro)
        }}
    }} catch(err) {{
        println "ERROR:Got exception while running $script:"
        println err
        throw err
    }} finally {{
        dir(project) {{
            sh """\
                cp $reposync_config exported-artifacts
                cp '$extra_sources' exported-artifacts
            """
        }}
        run_script('jenkins/jobs/confs/shell-scripts/mock_cleanup.sh')
    }}
}}

def prepare_suites_list(suits, suites_to_run, version, project){{
       dir(project) {{
       println "### Looking for suites ###"
       for (suit in suits)
           if (fileExists("automation/${{suit}}_suite_${{version}}.sh"))
               suites_to_run << suit
       }}
}}

def checkout(project, git_project, git_jenkins, suits, version, suites_to_run) {{
   println "### Downloading code ###"
   println "$project, $git_project, $git_jenkins"
   wrap([$class: 'TimestamperBuildWrapper']){{
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

def prepare_env(project,
                git_project,
                git_jenkins,
                suits,
                version,
                suites_to_run) {{
    println "### Preparing the environment ###"
    println "$project, $git_project, $git_jenkins"
    node ('fc23 || el7') {{
        checkout(project,
                 git_project,
                 git_jenkins,
                 suits,
                 version,
                 suites_to_run)
        prepare_suites_list(suits, suites_to_run, version, project)
    }}
}}

def run_checks(
    version,
    suits,
    distros,
    project,
    git_project,
    git_jenkins,
    extra_repo_url
) {{
    println "############################# Running checks"
    if (suits.isEmpty())
        return
    def branches = [:]
    for (int i = 0; i < suits.size(); i++) {{
        for (int j = 0; j < distros.size(); j++) {{
            def suit = "${{suits[i]}}"
            def distro = "${{distros[j]}}"
            def suit_dir = "$suit-suit-$version-$distro"
            def my_project = "$project"
            branches["${{suit}}_suit_${{distro}}"] = {{
                node('integ-tests') {{
                    wrap([$class: 'TimestamperBuildWrapper']) {{
                        try {{
                               sh 'rm -rf ./*'
                               unstash 'sources'
                               sh 'tar xzf sources.tar.gz'
                               run_mock_script(
                                "$version",
                                "$suit",
                                "$distro",
                                "$git_jenkins",
                                "$my_project",
                                "$git_project",
                                "$extra_repo_url",
                               )
                        }} catch(err) {{
                            println err
                            currentBuild.result = 'FAILURE'
                        }}
                        sh """\
                            rm -rf './$suit_dir'
                            if [[ -d './$my_project/exported-artifacts' ]]; then
                                sudo chown -R "\$USER:\$USER" './$my_project/exported-artifacts'
                                mv './$my_project/exported-artifacts' './$suit_dir'
                            fi
                            mkdir -p './$suit_dir'
                            if [[ -d ./exported-artifacts ]]; then
                                mv ./exported-artifacts './$suit_dir'
                            fi
                        """.stripIndent()
                        println "stashing $suit-$distro"
                        stash(
                            includes: "$suit_dir/**,$suit_dir/*",
                            name: "$suit-$distro"
                        )
                    }}
                }}
            }}
        }}
    }}
    parallel branches
}}


def do_archive(suits, distros) {{
    println "############################# Archiving"
    node {{
        wrap([$class: 'TimestamperBuildWrapper']) {{
            sh 'rm -rf *'
            sh 'mkdir exported-artifacts'
            for (int i = 0; i < suits.size(); i++) {{
                for (int j = 0; j < distros.size(); j++) {{
                    def suit = "${{suits[i]}}"
                    def distro = "${{distros[j]}}"
                    dir('exported-artifacts') {{
                        println "unstashing $suit-$distro"
                        unstash "$suit-$distro"
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
    suits,
    test_repo_url,
    credentials_prepare_test,
    credentials_ack_repo,
    suites_to_run
) {{
    stage concurrency: 1, name: 'Testing latest repo'
    try {{
      prepare_test_repo(deploy_server_url, version, credentials_prepare_test)
      prepare_env(
                  project,
                  git_project,
                  git_jenkins,
                  suits,
                  version,
                  suites_to_run
                )
      run_checks(
          version,
          suites_to_run,
          distros,
          project,
          git_project,
          git_jenkins,
          test_repo_url,
      )
      do_archive(suites_to_run, distros)
    }} catch(err) {{
        currentBuild.result = 'FAILURE'
        throw(err)
       }}
      finally {{
          if (currentBuild.result != 'FAILURE') {{
              ack_test_repo(deploy_server_url, version, credentials_ack_repo)
              if (currentBuild.rawBuild.getPreviousCompletedBuild()?.getResult().toString() == 'FAILURE') {{
                  notify(project, 'SUCCESS')
              }}
          }} else {{
                 println "Not promoting testing repo, as current build is '${{currentBuild.result}}'"
                 notify(project, currentBuild.result)
             }}
      }}
}}

main(
    project,
    git_project,
    git_jenkins,
    distros,
    version,
    deploy_server_url,
    suits,
    test_repo_url,
    credentials_prepare_test,
    credentials_ack_repo,
    suites_to_run
)
