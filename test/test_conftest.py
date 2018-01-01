#!/usr/bin/env python
"""test_usrc.py - Tests fixtures in conftest.py
"""


def test_gitrepo(gitrepo, git_at):
    repo = gitrepo(
        'tst_repo',
        {
            'msg': 'First commit',
            'files': {
                'fil1.txt': 'Text of fil1',
                'fil2.txt': 'Text of fil2',
                'fil5.txt': None,
            },
        },
        {
            'msg': 'Second commit',
            'files': {
                'fil2.txt': 'Modified text of fil2',
                'fil3.txt': 'Text of fil3',
                'fil5.txt': 'Text of fil5',
            },
        },
    )
    assert (repo / '.git').isdir()
    assert (repo / 'fil1.txt').isfile()
    assert (repo / 'fil1.txt').read() == 'Text of fil1'
    assert (repo / 'fil2.txt').isfile()
    assert (repo / 'fil2.txt').read() == 'Modified text of fil2'
    assert (repo / 'fil3.txt').isfile()
    assert (repo / 'fil3.txt').read() == 'Text of fil3'
    assert (repo / 'fil5.txt').isfile()
    assert (repo / 'fil5.txt').read() == 'Text of fil5'
    repogit = git_at(repo)
    assert repogit('status', '--short') == ''
    assert repogit('status', '-v').splitlines()[0].endswith('On branch master')
    log = repogit('log', '--pretty=format:%s').splitlines()
    assert len(log) == 2
    assert log == ['Second commit', 'First commit']
    # Test adding commits to existing repo during test
    gitrepo(
        'tst_repo',
        {
            'msg': 'Third commit',
            'files': {
                'fil3.txt': 'Modified text of fil3',
                'fil4.txt': 'Text of fil4',
                'fil5.txt': None,
            },
        },
    )
    assert (repo / 'fil1.txt').isfile()
    assert (repo / 'fil1.txt').read() == 'Text of fil1'
    assert (repo / 'fil2.txt').isfile()
    assert (repo / 'fil2.txt').read() == 'Modified text of fil2'
    assert (repo / 'fil3.txt').isfile()
    assert (repo / 'fil3.txt').read() == 'Modified text of fil3'
    assert (repo / 'fil4.txt').isfile()
    assert (repo / 'fil4.txt').read() == 'Text of fil4'
    assert not (repo / 'fil5.txt').exists()
    assert repogit('status', '--short') == ''
    log = repogit('log', '--pretty=format:%s').splitlines()
    assert len(log) == 3
    assert log == ['Third commit', 'Second commit', 'First commit']
    gitrepo('tst_repo', {'msg': 'Fourth empty commit'})
    log = repogit('log', '--pretty=format:%s').splitlines()
    assert len(log) == 4
    assert log == [
        'Fourth empty commit', 'Third commit', 'Second commit', 'First commit'
    ]
