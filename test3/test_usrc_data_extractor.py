import pytest
from stdci_tools import usrc_data_extractor as ude


@pytest.mark.parametrize('repo_url,expected_project_name', (
    (
        'https://some-repo/org/project-name',
        'PROJECT_NAME'
    ),
    (
        'https://some-repo/org/PROJECT-name',
        'PROJECT_NAME'
    ),
    (
        'https://some-repo/PROJECT-name.git',
        'PROJECT_NAME'
    ),
    (
        'https://some-repo/PROJECT.name-with.git.git',
        'PROJECT_NAME_WITH_GIT'
    ),
    (
        'PROJECT.name-with.git.git',
        'PROJECT_NAME_WITH_GIT'
    ),
    (
        'https://PROJECT-name',
        'PROJECT_NAME'
    ),
    (
        'https://some-repo/org/PROJECT_NAME',
        'PROJECT_NAME'
    ),
))
def test_project_name_from_repo_url(repo_url, expected_project_name):
    ret = ude.project_name_from_repo_url(repo_url)
    assert ret == expected_project_name


def test_project_name_from_repo_url_exception():
    excmsg = \
        "Failed to extract project name from repo URL. Repo URL can't be empty"
    with pytest.raises(ValueError, match=excmsg):
        ude.project_name_from_repo_url('')



@pytest.mark.parametrize('cfg_entry,legacy_name,expected_result', (
    (
        {
            'branch': 'some-branch',
            'commit': 'some-commit-id',
            'url': 'https://seom-repo/org/project-name'
        },
        False,
        (
            'CI_PROJECT_NAME_UPSTREAM_BRANCH=some-branch\n'
            'CI_PROJECT_NAME_UPSTREAM_COMMIT=some-commit-id\n'
            'CI_PROJECT_NAME_UPSTREAM_URL=https://seom-repo/org/project-name\n'
        )
    ),
    (
        {
            'branch': 'some-BRANCH.1.2.3',
            'commit': 'some-commit-ID.1.2.3',
            'url': 'https://seom-repo/org/project-NAME'
        },
        False,
        (
            'CI_PROJECT_NAME_UPSTREAM_BRANCH=some-BRANCH.1.2.3\n'
            'CI_PROJECT_NAME_UPSTREAM_COMMIT=some-commit-ID.1.2.3\n'
            'CI_PROJECT_NAME_UPSTREAM_URL=https://seom-repo/org/project-NAME\n'
        )
    ),
    (
        {
            'branch': 'some-BRANCH.1.2.3',
            'commit': 'some-commit-ID.1.2.3',
            'url': 'https://seom-repo/org/project-NAME'
        },
        True,
        (
            'CI_UPSTREAM_BRANCH=some-BRANCH.1.2.3\n'
            'CI_UPSTREAM_COMMIT=some-commit-ID.1.2.3\n'
            'CI_UPSTREAM_URL=https://seom-repo/org/project-NAME\n'
        )
    ),
))
def test_generate_entry_for_upstream_source(
    cfg_entry, legacy_name, expected_result
):
    ret = ude.generate_entry_for_upstream_source(1, cfg_entry, legacy_name)
    assert ret == expected_result


@pytest.mark.parametrize('cfg_entry,missing_entry', (
    (
        {
            'commit': 'some-commit-id',
            'url': 'https://seom-repo/org/project-name'
        },
        'branch'
    ),
    (
        {
            'branch': 'some-branch',
            'url': 'https://seom-repo/org/project-name'
        },
        'commit'
    ),
    (
        {
            'branch': 'some-branch',
            'commit': 'some-commit-id'
        },
        'url'
    ),
))
def test_generate_entry_for_upstream_source_exception(cfg_entry, missing_entry):
    excmsg = f'Missing {missing_entry} in upstream source entry #1.'
    with pytest.raises(KeyError, match=excmsg):
        ude.generate_entry_for_upstream_source(1, cfg_entry)


@pytest.mark.parametrize('usrc_config,expected_result', (
    (
        {
            'git': [
                {
                    'branch': 'branch-1',
                    'commit': 'commit-1',
                    'url': 'https://seom-repo/org/project-1'
                },
                {
                    'branch': 'branch-2',
                    'commit': 'commit-2',
                    'url': 'https://seom-repo/org/project-2'
                },
                {
                    'branch': 'branch-3',
                    'commit': 'commit-3',
                    'url': 'https://seom-repo/project-3'
                },
            ]
        },
        (
            'CI_PROJECT_1_UPSTREAM_BRANCH=branch-1\n'
            'CI_PROJECT_1_UPSTREAM_COMMIT=commit-1\n'
            'CI_PROJECT_1_UPSTREAM_URL=https://seom-repo/org/project-1\n'
            'CI_PROJECT_2_UPSTREAM_BRANCH=branch-2\n'
            'CI_PROJECT_2_UPSTREAM_COMMIT=commit-2\n'
            'CI_PROJECT_2_UPSTREAM_URL=https://seom-repo/org/project-2\n'
            'CI_PROJECT_3_UPSTREAM_BRANCH=branch-3\n'
            'CI_PROJECT_3_UPSTREAM_COMMIT=commit-3\n'
            'CI_PROJECT_3_UPSTREAM_URL=https://seom-repo/project-3\n'
            'CI_UPSTREAM_BRANCH=branch-1\n'
            'CI_UPSTREAM_COMMIT=commit-1\n'
            'CI_UPSTREAM_URL=https://seom-repo/org/project-1\n'
        )
    ),
    (
        {
            'git': [
                {
                    'branch': 'branch-1',
                    'commit': 'commit-1',
                    'url': 'https://seom-repo/org/project-1'
                },
                {
                    'branch': 'branch-2',
                    'commit': 'commit-2',
                    'url': 'https://seom-repo/org/project-2'
                },
                {
                    'branch': 'branch-3',
                    'commit': 'commit-3',
                    'url': 'https://seom-repo/org/project-1'
                },
            ]
        },
        (
            'CI_PROJECT_1_UPSTREAM_BRANCH=branch-1\n'
            'CI_PROJECT_1_UPSTREAM_COMMIT=commit-1\n'
            'CI_PROJECT_1_UPSTREAM_URL=https://seom-repo/org/project-1\n'
            'CI_PROJECT_2_UPSTREAM_BRANCH=branch-2\n'
            'CI_PROJECT_2_UPSTREAM_COMMIT=commit-2\n'
            'CI_PROJECT_2_UPSTREAM_URL=https://seom-repo/org/project-2\n'
            'CI_PROJECT_1_UPSTREAM_BRANCH=branch-3\n'
            'CI_PROJECT_1_UPSTREAM_COMMIT=commit-3\n'
            'CI_PROJECT_1_UPSTREAM_URL=https://seom-repo/org/project-1\n'
            'CI_UPSTREAM_BRANCH=branch-1\n'
            'CI_UPSTREAM_COMMIT=commit-1\n'
            'CI_UPSTREAM_URL=https://seom-repo/org/project-1\n'
        )
    ),
))
def test_generate_environment_file(usrc_config, expected_result):
    ret = ude.generate_environment_file(usrc_config)
    assert ret == expected_result


@pytest.mark.parametrize('cfg,excmsg', (
    ([], "upstream sources config should be a dict, not <class 'list'>"),
    ("", "upstream sources config should be a dict, not <class 'str'>"),
    (1, "upstream sources config should be a dict, not <class 'int'>"),
))
def test_generate_environment_file_wrong_cfg_type_exception(cfg, excmsg):
    with pytest.raises(TypeError, match=excmsg):
        ude.generate_environment_file(cfg)


def test_generate_environment_file_missing_git_entry_exception():
    excmsg = 'Missing `git` config entry in upstream_sources.yaml.'
    with pytest.raises(KeyError, match=excmsg):
        ude.generate_environment_file({})


@pytest.mark.parametrize('input', [None, 'my-config.yaml'])
def test_load_upstream_sources_yaml(input, tmpdir, monkeypatch):
    config_name = input or "upstream_sources.yaml"
    config_path = tmpdir / config_name
    config_path.write('key: value')
    monkeypatch.chdir(tmpdir)
    parsed = ude.load_upstream_sources_yaml(input)
    assert parsed['key'] == 'value'