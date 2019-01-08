"""test_jjb_jobs_xml.py - Tests for the jjb_jobs_xml lookup plugin
"""
import pytest
from textwrap import dedent
import yaml

from jjb_jobs_xml import LookupModule


@pytest.fixture
def jjb_yaml(tmpdir):
    yaml_dir = tmpdir / 'jjb_yaml'
    (yaml_dir / 'yaml' / 'template.yaml').write_text(dedent(
        """
        - job-template:
            name: hello-{who}
            project-type: pipeline
            properties:
            - inject:
                properties-content: |
                  WHO={who}
            dsl: !include-raw-escape: groovy/hello.groovy
        """
    ).lstrip(), 'utf8', ensure=True)
    (yaml_dir / 'projects' / 'projects.yaml').write_text(dedent(
        """
        - project:
            name: hello
            who:
            - world
            - sir
            jobs:
            - hello-{who}
        """
    ).lstrip(), 'utf8', ensure=True)
    (yaml_dir / 'groovy' / 'hello.groovy').write_text(dedent(
        """
        echo "Hello ${env.WHO}"
        """
    ).lstrip(), 'utf8', ensure=True)
    return yaml_dir


@pytest.fixture
def jjb_xml():
    return {
        'hello-world':
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<flow-definition plugin="workflow-job">\n'
            '  <definition '
            'class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" '
            'plugin="workflow-cps">\n'
            '    <script>echo &quot;Hello ${env.WHO}&quot;\n'
            '</script>\n'
            '    <sandbox>false</sandbox>\n'
            '  </definition>\n'
            '  <actions/>\n'
            '  <description>&lt;!-- Managed by Jenkins Job Builder '
            '--&gt;</description>\n'
            '  <keepDependencies>false</keepDependencies>\n'
            '  '
            '<blockBuildWhenDownstreamBuilding>false'
            '</blockBuildWhenDownstreamBuilding>\n'
            '  '
            '<blockBuildWhenUpstreamBuilding>false'
            '</blockBuildWhenUpstreamBuilding>\n'
            '  <concurrentBuild>false</concurrentBuild>\n'
            '  <canRoam>true</canRoam>\n'
            '  <properties>\n'
            '    <EnvInjectJobProperty>\n'
            '      <info>\n'
            '        <propertiesContent>WHO=world\n'
            '</propertiesContent>\n'
            '        <loadFilesFromMaster>false</loadFilesFromMaster>\n'
            '      </info>\n'
            '      <on>true</on>\n'
            '      <keepJenkinsSystemVariables>true'
            '</keepJenkinsSystemVariables>\n'
            '      <keepBuildVariables>true</keepBuildVariables>\n'
            '      <overrideBuildParameters>false'
            '</overrideBuildParameters>\n'
            '    </EnvInjectJobProperty>\n'
            '  </properties>\n'
            '  <scm class="hudson.scm.NullSCM"/>\n'
            '  <publishers/>\n'
            '  <buildWrappers/>\n'
            '</flow-definition>\n',
        'hello-sir':
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<flow-definition plugin="workflow-job">\n'
            '  <definition '
            'class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" '
            'plugin="workflow-cps">\n'
            '    <script>echo &quot;Hello ${env.WHO}&quot;\n'
            '</script>\n'
            '    <sandbox>false</sandbox>\n'
            '  </definition>\n'
            '  <actions/>\n'
            '  <description>&lt;!-- Managed by Jenkins Job Builder '
            '--&gt;</description>\n'
            '  <keepDependencies>false</keepDependencies>\n'
            '  '
            '<blockBuildWhenDownstreamBuilding>false'
            '</blockBuildWhenDownstreamBuilding>\n'
            '  '
            '<blockBuildWhenUpstreamBuilding>false'
            '</blockBuildWhenUpstreamBuilding>\n'
            '  <concurrentBuild>false</concurrentBuild>\n'
            '  <canRoam>true</canRoam>\n'
            '  <properties>\n'
            '    <EnvInjectJobProperty>\n'
            '      <info>\n'
            '        <propertiesContent>WHO=sir\n'
            '</propertiesContent>\n'
            '        <loadFilesFromMaster>false</loadFilesFromMaster>\n'
            '      </info>\n'
            '      <on>true</on>\n'
            '      <keepJenkinsSystemVariables>true'
            '</keepJenkinsSystemVariables>\n'
            '      <keepBuildVariables>true</keepBuildVariables>\n'
            '      <overrideBuildParameters>false'
            '</overrideBuildParameters>\n'
            '    </EnvInjectJobProperty>\n'
            '  </properties>\n'
            '  <scm class="hudson.scm.NullSCM"/>\n'
            '  <publishers/>\n'
            '  <buildWrappers/>\n'
            '</flow-definition>\n'
    }


class TestLookupModule(object):
    @pytest.fixture
    def instance(self):
        return LookupModule()

    def test_plugin_info_file(self, instance):
        plugin_info = ['some', 'data']
        with instance.plugin_info_file(plugin_info) as pif:
            with open(pif, 'r') as f:
                out = yaml.load(f)
                assert out == plugin_info

    def test_no_plugin_info_file(self, instance):
        with instance.plugin_info_file(None) as pif:
            with open(pif, 'r') as f:
                out = yaml.load(f)
                assert out == []

    def test_run(self, instance, jjb_yaml):
        expected = {}
        result = instance.run(
            ['.'],
            chdir=str(jjb_yaml),
        )
        assert result == expected

    def test_run_dirnames(self, instance, jjb_yaml, jjb_xml):
        expected = jjb_xml
        result = instance.run(
            ['projects:yaml'],
            chdir=str(jjb_yaml),
        )
        assert result == expected

    def test_run_recursive(self, instance, jjb_yaml, jjb_xml):
        expected = jjb_xml
        result = instance.run(
            ['.'],
            chdir=str(jjb_yaml),
            recursive=True,
        )
        assert result == expected

    def test_run_recursive_filtered(self, instance, jjb_yaml, jjb_xml):
        expected = {'hello-world': jjb_xml['hello-world']}
        result = instance.run(
            ['.', '*world*'],
            chdir=str(jjb_yaml),
            recursive=True,
        )
        assert result == expected

    def test_run_missing_dir(self, instance, jjb_yaml):
        expected = {}
        result = instance.run(
            ['yaml'],
            chdir=str(jjb_yaml),
        )
        assert result == expected
