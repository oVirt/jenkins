"""test_decorate.py - Tests for decorate.sh

While `decorate.sh` is a shell script, the tests are written in Python to take
advantage of the capabilities of pytest
"""
import pytest
from glob import glob
import os
from textwrap import dedent
import py

from scripts.decorate import decorate

@pytest.fixture
def exported_artifacts(tmpdir, monkeypatch):
    ea_dir = tmpdir / 'exported-artifacts'
    ea_dir.ensure_dir()
    monkeypatch.setenv('EXPORTED_ARTIFACTS', str(ea_dir))
    return ea_dir

@pytest.fixture(params=[True, False])
def extra_sources(exported_artifacts, request):
    if request.param:
        content = dedent(
            """
            some/source/url
            another/source/url
            """
        ).lstrip()
        (exported_artifacts / 'extra_sources').write(content)
        return content
    return None

@pytest.fixture
def yumrepos_normal():
    return dedent(
        """
        [repo1]
        baseurl = http://some/repo/url
        """
    ).lstrip()

@pytest.fixture
def yumrepos_injected():
    return dedent(
        """
        [repo1]
        baseurl = http://some/mirror/url
        proxy = None

        """
    ).lstrip()

@pytest.fixture(params=[True, False])
def mirrors_cfg(exported_artifacts, request):
    if request.param:
        (exported_artifacts / 'mirrors.yaml').write(dedent(
            """
            ---
            repo1: http://some/mirror/url
            """
        ).lstrip())
    return request.param

@pytest.fixture
def upstream(gitrepo, yumrepos_normal):
    return gitrepo(
        'upstream',
        {
            'msg': 'First US commit',
            'files': {
                'us_file1.txt': 'Upstream content',
                'us_file2.txt': 'More us content',
                'automation/script1.sh': 'some script',
                'automation/script1.yumrepos': yumrepos_normal,
                'automation/script1.more.yumrepos': yumrepos_normal,
            },
        },
    )

@pytest.fixture
def downstream(gitrepo, upstream, git_last_sha, yumrepos_normal, monkeypatch):
    sha = git_last_sha(upstream)
    repo = gitrepo(
        'downstream',
        {
            'msg': 'First DS commit',
            'files': {
                'ds_file.txt': 'Downstream content',
                'automation/script1.yumrepos.el7': yumrepos_normal,
                'automation/script1.yumrepos.el8': yumrepos_normal,
                'automation/upstream_sources.yaml': dedent(
                    """
                    ---
                    git:
                      - url: {upstream}
                        commit: {sha}
                        branch: master
                    """
                ).lstrip().format(upstream=str(upstream), sha=sha),
            },
        },
    )
    monkeypatch.setenv('STD_CI_CLONE_URL', str(repo))
    monkeypatch.setenv('STD_CI_REFSPEC', 'refs/heads/master')
    return repo

@pytest.fixture
def workspace(monkeypatch, tmpdir):
    ws = tmpdir / 'workspace'
    ws.ensure_dir()
    monkeypatch.chdir(ws)
    return ws

@pytest.mark.parametrize(
    'std_ci_script,std_ci_distro,exp_script_executable,exp_injected_files',
[
    (
        'automation/script1.sh',
        'el7',
        True,
        {
            'automation/script1.more.yumrepos',
            'automation/script1.yumrepos',
            'automation/script1.yumrepos.el7',
        },
    ),
    (
        'automation/script1.sh',
        'el8',
        True,
        {
            'automation/script1.more.yumrepos',
            'automation/script1.yumrepos',
            'automation/script1.yumrepos.el8',
        },
    ),
    (
        'automation/script1.sh',
        'fc30',
        True,
        {
            'automation/script1.more.yumrepos',
            'automation/script1.yumrepos',
        },
    ),
    ('automation/does_not_exist.sh', 'el7', False, set()),
    (None, 'el7', False, set()),
])
def test_decorate(
    monkeypatch, workspace, downstream, mirrors_cfg, yumrepos_normal,
    yumrepos_injected, extra_sources, exported_artifacts, std_ci_script,
    std_ci_distro, exp_script_executable, exp_injected_files,
):
    if std_ci_script is None:
        monkeypatch.delenv('STD_CI_SCRIPT', raising=False)
        monkeypatch.delenv('STD_CI_DISTRO', raising=False)
    else:
        monkeypatch.setenv('STD_CI_SCRIPT', std_ci_script)
        monkeypatch.setenv('STD_CI_DISTRO', std_ci_distro)
    expected_files = [
        'automation',
        'automation/script1.more.yumrepos',
        'automation/script1.sh',
        'automation/script1.yumrepos',
        'automation/script1.yumrepos.el7',
        'automation/script1.yumrepos.el8',
        'automation/upstream_sources.yaml',
        'ds_file.txt',
        'us_file1.txt',
        'us_file2.txt',
    ]
    if extra_sources:
        expected_files.append('extra_sources')
        expected_files.sort()
    if not mirrors_cfg:
        exp_injected_files = set()
    all_yumrepos = {
        'automation/script1.more.yumrepos',
        'automation/script1.yumrepos',
        'automation/script1.yumrepos.el7',
        'automation/script1.yumrepos.el8',
    }
    assert sorted(glob('**', recursive=True)) == []

    decorate()

    assert sorted(glob('**', recursive=True)) == expected_files
    assert exp_script_executable == \
        os.access(str(workspace/'automation'/'script1.sh'), os.X_OK)
    es_out = workspace/'extra_sources'
    if extra_sources:
        assert es_out.exists()
        assert es_out.read() == extra_sources
        assert (exported_artifacts/'extra_sources').exists()
    else:
        assert not es_out.exists()
    for yumrepos_file in all_yumrepos:
        if yumrepos_file in exp_injected_files:
            assert (workspace/yumrepos_file).read() == yumrepos_injected
            assert (
                exported_artifacts/'yumrepos'/os.path.basename(yumrepos_file)
            ).read() == yumrepos_injected
        else:
            assert (workspace/yumrepos_file).read() == yumrepos_normal
    if mirrors_cfg:
        assert (exported_artifacts / 'mirrors.yaml').exists()
