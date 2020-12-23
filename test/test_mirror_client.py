#!/usr/bin/env python
"""test_mirror_client.py - Tests for mirror_client.py
"""
import socket
from textwrap import dedent
from six.moves import StringIO
import pytest
from six.moves.BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import json
import yaml
from threading import Thread
from six.moves.urllib.parse import urljoin
import requests
from time import sleep
from random import randrange
from os import environ
try:
    from unittest.mock import MagicMock, call, sentinel
except ImportError:
    from mock import MagicMock, call, sentinel

from stdci_libs.mirror_client import (
    inject_yum_mirrors, inject_yum_mirrors_str, mirrors_from_http,
    mirrors_from_file, mirrors_from_data_url, mirrors_from_uri,
    parse_mirror_includes, merge_mirrors, mirrors_from_environ,
    ovirt_tested_as_mirrors, none_value_by_repo_name, normalize_mirror_urls,
    mirrors_to_inserts,
)


@pytest.fixture
def orig_repos_cfg():
    return dedent(
        """
        [main]
        gpgcheck=0

        [plain_mirrored_repo]
        name=A plain mirrored repo
        baseurl=http://example.com/yum/repo/el$releasever/$basearch

        [list_mirrored_repo]
        name=A mirrored repo with an (upstream) mirror list
        mirrorlist=http://example.com/yum/mirrorlist
        failovermethod=priority

        [metalink_mirrored_repo]
        name=A mirrored repo with a metalink configuration
        metalink=http://example.com/dnf/metalink
        failovermethod=priority

        [unmirrored_repo]
        name=A non-mirrored repo
        baseurl=http://example.com/yum/another_repo
        enabled=1

        [unmirrored_repo_w_insert]
        name=A non-mirrored repo that get an insert
        baseurl=http://example.com/yum/one_more_repo
        enabled=1
        """
    ).lstrip()


@pytest.fixture
def mirrors_dict():
    return dict(
        plain_mirrored_repo='http://mirror.com/yum/repo',
        list_mirrored_repo='http://mirror.com/yum/list_repo',
        metalink_mirrored_repo='http://mirror.com/yum/metalink_repo',
        **{
            'before:list_mirrored_repo': [
                ['inserted1', 'http://localhost/inserted1'],
            ],
            'before:unmirrored_repo_w_insert': [
                ['inserted2', 'http://localhost/inserted2'],
            ],
            'before:non_existant_repo': [
                ['inserted3', 'http://localhost/inserted3'],
            ],
        }
    )


@pytest.fixture
def expected_repos_cfg():
    return dedent(
        """
        [main]
        gpgcheck = 0

        [plain_mirrored_repo]
        name = A plain mirrored repo
        baseurl = http://mirror.com/yum/repo
        proxy = None

        [inserted1]
        baseurl = http://localhost/inserted1
        proxy = None

        [list_mirrored_repo]
        name = A mirrored repo with an (upstream) mirror list
        failovermethod = priority
        baseurl = http://mirror.com/yum/list_repo
        proxy = None

        [metalink_mirrored_repo]
        name = A mirrored repo with a metalink configuration
        failovermethod = priority
        baseurl = http://mirror.com/yum/metalink_repo
        proxy = None

        [unmirrored_repo]
        name = A non-mirrored repo
        baseurl = http://example.com/yum/another_repo
        enabled = 1

        [inserted2]
        baseurl = http://localhost/inserted2
        proxy = None

        [unmirrored_repo_w_insert]
        name = A non-mirrored repo that get an insert
        baseurl = http://example.com/yum/one_more_repo
        enabled = 1

        """
    ).lstrip()


@pytest.fixture
def expected_repos_proxied_cfg():
    return dedent(
        """
        [main]
        gpgcheck = 0

        [plain_mirrored_repo]
        name = A plain mirrored repo
        baseurl = http://mirror.com/yum/repo

        [inserted1]
        baseurl = http://localhost/inserted1

        [list_mirrored_repo]
        name = A mirrored repo with an (upstream) mirror list
        failovermethod = priority
        baseurl = http://mirror.com/yum/list_repo

        [metalink_mirrored_repo]
        name = A mirrored repo with a metalink configuration
        failovermethod = priority
        baseurl = http://mirror.com/yum/metalink_repo

        [unmirrored_repo]
        name = A non-mirrored repo
        baseurl = http://example.com/yum/another_repo
        enabled = 1

        [inserted2]
        baseurl = http://localhost/inserted2

        [unmirrored_repo_w_insert]
        name = A non-mirrored repo that get an insert
        baseurl = http://example.com/yum/one_more_repo
        enabled = 1

        """
    ).lstrip()


@pytest.fixture
def mirror_server(mirrors_dict):
    mirror_file_path = '/mirrors.json'
    mirror_corrupt_file_path = '/corrupt_mirrors.json'
    mirror_json_varname = 'ci_repos'
    mirror_data = {mirror_json_varname: mirrors_dict}
    mirror_json = json.dumps(mirror_data).encode('utf8')

    class MirrorRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == mirror_file_path:
                self.send_response(200)
                self.send_header("Content-type", 'application/json')
                self.end_headers()
                self.wfile.write(mirror_json)
            elif self.path == mirror_corrupt_file_path:
                self.send_response(200)
                self.send_header("Content-type", 'application/json')
                self.end_headers()
                self.wfile.write('{"this": "is", "bad": "json"')
            else:
                self.send_error(404)

    for attempt in range(0, 20):
        server_address = ('127.0.0.1', randrange(8765, 8876))
        try:
            server = HTTPServer(server_address, MirrorRequestHandler)
        except socket.error as e:
            if e.errno == 98:
                continue
            raise
        break
    else:
        raise RuntimeError("Failed to allocate port for mirror_server fixture")

    server_url = 'http://{0}:{1}'.format(*server_address)

    sthread = Thread(target=server.serve_forever)
    sthread.start()
    try:
        # Wait for http server to start
        sleep(0.1)
        # ensure we won't implictly try to use proxies to access local server
        old_env = dict((
            (k, environ.pop(k))
            for k in ('http_proxy', 'HTTP_PROXY') if k in environ
        ))
        try:
            yield dict(
                mirror_url=urljoin(server_url, mirror_file_path),
                json_varname=mirror_json_varname,
                bad_path_url=urljoin(server_url, '/bad_file'),
                bad_port_url=urljoin(
                    'http://{0}:8764'.format(server_address[0]),
                    mirror_file_path
                ),
                corrupt_url=urljoin(server_url, mirror_corrupt_file_path),
            )
        finally:
            environ.update(old_env)
    finally:
        server.shutdown()
        sthread.join()


def test_inject_yum_mirrors(
    orig_repos_cfg, mirrors_dict, expected_repos_cfg,
    expected_repos_proxied_cfg
):
    my_out_fil = StringIO()
    inject_yum_mirrors(mirrors_dict, StringIO(orig_repos_cfg), my_out_fil)
    my_out_fil.seek(0)
    assert expected_repos_cfg == my_out_fil.read()
    # Test when proxies are allowed
    my_out_fil = StringIO()
    inject_yum_mirrors(
        mirrors_dict, StringIO(orig_repos_cfg), my_out_fil, True
    )
    my_out_fil.seek(0)
    assert expected_repos_proxied_cfg == my_out_fil.read()


@pytest.mark.parametrize('repo_name, expected', [
    ('centos-base-el7', '_none_'),
    ('fedora-base-fc27', '_none_'),
    ('fedora-base-fc28', '_none_'),
    ('fedora-base-fc29', 'None'),
    ('fedora-base-fc30', 'None'),
    ('no-suffix', 'None'),
    ('bad-suffix-fc', 'None'),
])
def test_none_value_by_repo_name(repo_name, expected):
    out = none_value_by_repo_name(repo_name)
    assert out == expected


def test_inject_yum_mirrors_str(
    orig_repos_cfg, mirrors_dict, expected_repos_cfg,
    expected_repos_proxied_cfg
):
    output = inject_yum_mirrors_str(mirrors_dict, orig_repos_cfg)
    assert expected_repos_cfg == output
    # Test when proxies are allowed
    output = inject_yum_mirrors_str(mirrors_dict, orig_repos_cfg, True)
    assert expected_repos_proxied_cfg == output


def test_mirror_server_fixture(mirror_server, mirrors_dict):
    resp = requests.get(mirror_server['mirror_url'])
    assert resp.status_code == 200
    assert resp.json() == \
        {mirror_server['json_varname']: mirrors_dict}
    resp = requests.get(mirror_server['bad_path_url'])
    assert resp.status_code != 200
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(mirror_server['bad_port_url'])
    resp = requests.get(mirror_server['corrupt_url'])
    assert resp.status_code == 200


def test_mirrors_from_http(mirror_server, mirrors_dict):
    result = mirrors_from_http(
        mirror_server['mirror_url'], mirror_server['json_varname']
    )
    assert result == mirrors_dict
    result = mirrors_from_http(mirror_server['bad_path_url'])
    assert result == {}
    result = mirrors_from_http(mirror_server['bad_port_url'])
    assert result == {}
    with pytest.raises(ValueError):
        mirrors_from_http(mirror_server['corrupt_url'])


def test_mirrors_from_file(mirrors_dict, tmpdir):
    json_file = tmpdir.join('mirrors.json')
    with json_file.open('w') as f:
        json.dump(mirrors_dict, f)
    json_out = mirrors_from_file(str(json_file))
    assert id(mirrors_dict) != id(json_out)
    assert mirrors_dict == json_out
    yaml_file = tmpdir.join('mirrors.yaml')
    with yaml_file.open('w') as f:
        yaml.safe_dump(mirrors_dict, f)
    yaml_out = mirrors_from_file(str(yaml_file))
    assert id(mirrors_dict) != id(yaml_out)
    assert id(json_out) != id(yaml_out)
    assert mirrors_dict == yaml_out


def test_mirrors_from_bad_file(tmpdir):
    bad_file = tmpdir.join('not_mirrors.txt')
    bad_file.write('--not-mirrors-data--')
    with pytest.raises(ValueError):
        mirrors_from_file(str(bad_file))


@pytest.mark.parametrize('url,expected', [
    (
        'data:application/json,{"foo": "bar", "baz": "bal"}',
        {"foo": "bar", "baz": "bal"}
    ),
    (
        'data:application/json;base64,eyJmb28iOiAiYmFyIiwgImJheiI6ICJiYWwifQ=='
        , {"foo": "bar", "baz": "bal"}
    ),
    ('http://foo.com/bar', {}),
    ('data:text/plain,{"foo": "bar", "baz": "bal"}', {}),
    ('data:{"foo": "bar", "baz": "bal"}', {}),
    ('data:;base64,eyJmb28iOiAiYmFyIiwgImJheiI6ICJiYWwifQ==', {}),
])
def test_mirrors_from_data_url(url, expected):
    out = mirrors_from_data_url(url)
    assert out == expected


def identity(x, *args, **kwargs):
    return x


def test_mirrors_from_uri_http(monkeypatch):
    mirrors_from_http = MagicMock(side_effect=[sentinel.http_mirrors])
    mirrors_from_file = MagicMock(side_effect=[sentinel.file_mirrors])
    mirrors_from_data_url = MagicMock(side_effect=[sentinel.data_mirrors])
    normalize_mirror_urls = MagicMock(side_effect=identity)
    parse_mirror_includes = MagicMock(side_effect=identity)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_http",
                        mirrors_from_http)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_file",
                        mirrors_from_file)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_data_url",
                        mirrors_from_data_url)
    monkeypatch.setattr("stdci_libs.mirror_client.normalize_mirror_urls",
                        normalize_mirror_urls)
    monkeypatch.setattr("stdci_libs.mirror_client.parse_mirror_includes",
                        parse_mirror_includes)
    http_url = 'http://mirrors.example.com'
    out = mirrors_from_uri(http_url)
    assert out == sentinel.http_mirrors
    assert mirrors_from_http.called
    assert mirrors_from_http.call_args == \
        call(http_url, 'latest_ci_repos', False)
    assert not mirrors_from_file.called
    assert not mirrors_from_data_url.called
    assert normalize_mirror_urls.called
    assert normalize_mirror_urls.call_args == \
        call(sentinel.http_mirrors, http_url)


@pytest.mark.parametrize(
    ('in_path', 'passed_path'),
    [
        ('/path/to/mirrors.yaml', '/path/to/mirrors.yaml'),
        ('file:///path/to/mirrors.yaml', '/path/to/mirrors.yaml'),
        ('path/to/mirrors.yaml', 'path/to/mirrors.yaml'),
    ]
)
def test_mirrors_from_uri_file(monkeypatch, in_path, passed_path):
    mirrors_from_http = MagicMock(side_effect=[sentinel.http_mirrors])
    mirrors_from_file = MagicMock(side_effect=[sentinel.file_mirrors])
    mirrors_from_data_url = MagicMock(side_effect=[sentinel.data_mirrors])
    normalize_mirror_urls = MagicMock(side_effect=identity)
    parse_mirror_includes = MagicMock(side_effect=identity)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_http",
                        mirrors_from_http)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_file",
                        mirrors_from_file)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_data_url",
                        mirrors_from_data_url)
    monkeypatch.setattr("stdci_libs.mirror_client.normalize_mirror_urls",
                        normalize_mirror_urls)
    monkeypatch.setattr("stdci_libs.mirror_client.parse_mirror_includes",
                        parse_mirror_includes)
    out = mirrors_from_uri(in_path)
    assert out == sentinel.file_mirrors
    assert mirrors_from_file.called
    assert mirrors_from_file.call_args == call(passed_path)
    assert not mirrors_from_http.called
    assert not mirrors_from_data_url.called
    assert normalize_mirror_urls.called
    assert normalize_mirror_urls.call_args == \
        call(sentinel.file_mirrors, in_path)


def test_mirrors_from_uri_data(monkeypatch):
    mirrors_from_http = MagicMock(side_effect=[sentinel.http_mirrors])
    mirrors_from_file = MagicMock(side_effect=[sentinel.file_mirrors])
    mirrors_from_data_url = MagicMock(side_effect=[sentinel.data_mirrors])
    normalize_mirror_urls = MagicMock(side_effect=identity)
    parse_mirror_includes = MagicMock(side_effect=identity)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_http",
                        mirrors_from_http)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_file",
                        mirrors_from_file)
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_data_url",
                        mirrors_from_data_url)
    monkeypatch.setattr("stdci_libs.mirror_client.normalize_mirror_urls",
                        normalize_mirror_urls)
    monkeypatch.setattr("stdci_libs.mirror_client.parse_mirror_includes",
                        parse_mirror_includes)
    data_url = 'data:application/json:{"foo": "bar"}'
    out = mirrors_from_uri(data_url)
    assert out == sentinel.data_mirrors
    assert mirrors_from_data_url.called
    assert mirrors_from_data_url.call_args == call(data_url)
    assert not mirrors_from_file.called
    assert not mirrors_from_http.called
    assert normalize_mirror_urls.called
    assert normalize_mirror_urls.call_args == \
        call(sentinel.data_mirrors, data_url)


@pytest.mark.parametrize('mirrors,expected', [
    (
        {
            u'repo1-el7': u'url1',
            u'include:': [
                u'data:application/json,' + json.dumps({
                    u'repo2-el7': u'url2',
                }),
            ]
        },
        {
            u'repo1-el7': u'url1',
            u'repo2-el7': u'url2',
        },
    ),
    (
        {
            u'repo1-el7': u'url1',
            u'before:repo1-el7': [[u'repo2-el7', u'url2']],
            u'include:': [
                u'data:application/json,' + json.dumps({
                    u'repo1-el7': u'url1a',
                    u'repo3-el7': u'url3a',
                    u'repo4-el7': u'url4a',
                    u'before:repo1-el7': [[u'repo5-el7', u'url5']],
                    u'before:repo3-el7': [[u'repo6-el7', u'url6']],
                }),
                u'data:application/json,' + json.dumps({
                    u'repo1-el7': u'url1b',
                    u'repo3-el7': u'url3b',
                    u'repo7-el7': u'url7b',
                    u'before:repo3-el7': [[u'repo8-el7', u'url8']],
                    u'include:': [
                        u'data:application/json,' + json.dumps({
                            u'repo9-el7': u'url9c',
                        }),
                    ]
                }),
            ],
            u'include:before:': [
                [u'repo1', u'data:application/json,' + json.dumps({
                    u'repo10-el7': u'url10',
                    u'repo11-el8': u'url11',
                })],
                [u'repo3', u'data:application/json,' + json.dumps({
                    u'repo12-el7': u'url12',
                })],
                [u'repo4', u'data:application/json,' + json.dumps({
                    u'repo13-el8': u'url13',
                })],
            ]
        },
        {
            u'repo1-el7': u'url1',
            u'before:repo1-el7': [
                [u'repo2-el7', u'url2'], [u'repo5-el7', u'url5'],
                [u'repo10-el7', u'url10'],
            ],
            u'before:repo1-el8': [
                [u'repo11-el8', u'url11'],
            ],
            u'repo3-el7': u'url3a',
            u'before:repo3-el7': [
                [u'repo6-el7', u'url6'], [u'repo8-el7', u'url8'],
                [u'repo12-el7', u'url12'],
            ],
            u'repo4-el7': u'url4a',
            u'before:repo4-el8': [
                [u'repo13-el8', u'url13'],
            ],
            u'repo7-el7': u'url7b',
            u'repo9-el7': u'url9c',
        }
    ),
])
def test_parse_mirror_includes(mirrors, expected):
    out = parse_mirror_includes(mirrors)
    assert out == expected


@pytest.mark.parametrize('a,b,expected', [(
    {
        'repo1': 'url1',
        'repo2': 'url2',
        'before:repo1': [['repo3', 'url3']],
        'before:repo2': [['repo4', 'url4']],
    },
    {
        'repo2': 'url2b',
        'repo5': 'url5',
        'before:repo2': [['repo6', 'url6'], ['repo7', 'url7']],
    },
    {
        'repo1': 'url1',
        'repo2': 'url2',
        'repo5': 'url5',
        'before:repo1': [['repo3', 'url3']],
        'before:repo2': [
            ['repo4', 'url4'], ['repo6', 'url6'], ['repo7', 'url7'],
        ],
    },
)])
def test_merge_mirrors(a, b, expected):
    out = merge_mirrors(a, b)
    assert out == expected


def test_mirrors_from_environ(monkeypatch):
    mirrors_from_uri = MagicMock(side_effect=[sentinel.some_mirrors])
    monkeypatch.setattr("stdci_libs.mirror_client.mirrors_from_uri",
                        mirrors_from_uri)
    monkeypatch.setenv('CI_MIRRORS_URL', 'some_mirrors_uri')
    out = mirrors_from_environ()
    assert out == sentinel.some_mirrors
    assert mirrors_from_uri.called
    assert mirrors_from_uri.call_args == call('some_mirrors_uri')


@pytest.mark.parametrize('mirrors,base_uri,expected', [
    (
        {
            'repo1': 'http://example.com/repo1',
            'repo2': '/repos/repo2',
            'repo3': 'packages/repo3',
            'before:repo3': [
                ['repo4', '/repos/repo4'],
                ['repo5', 'http://example.com/repo5'],
            ]
        },
        'https://foo.bar.com/mirrors/latest.json',
        {
            'repo1': 'http://example.com/repo1',
            'repo2': 'https://foo.bar.com/repos/repo2',
            'repo3': 'https://foo.bar.com/mirrors/packages/repo3',
            'before:repo3': [
                ['repo4', 'https://foo.bar.com/repos/repo4'],
                ['repo5', 'http://example.com/repo5'],
            ]
        },
    ),
])
def test_normalize_mirror_urls(mirrors, base_uri, expected):
    out = normalize_mirror_urls(mirrors, base_uri)
    assert out == expected


@pytest.mark.parametrize('mirrors,ins_repo_prefix,expected', [
    (
        {
            'repo1-el7': '/repo1/el7',
            'repo1-el8': '/repo1/el8',
            'repo1-fc30': '/repo1/fc30',
            'repo2-el7': '/repo2/el7',
            'before:target-fc30': [
                ['repo3-fc30', '/repo3/fc30'],
            ]
        },
        'target',
        {
            'before:target-el7': [
                ['repo1-el7', '/repo1/el7'],
                ['repo2-el7', '/repo2/el7'],
            ],
            'before:target-el8': [
                ['repo1-el8', '/repo1/el8'],
            ],
            'before:target-fc30': [
                ['repo3-fc30', '/repo3/fc30'],
                ['repo1-fc30', '/repo1/fc30'],
            ],
        },
    )
])
def test_mirrors_to_inserts(mirrors, ins_repo_prefix, expected):
    out = mirrors_to_inserts(mirrors, ins_repo_prefix)
    assert out == expected


def test_ovirt_tested_as_mirrors():
    expected = {
        'ovirt-master-el7':
            'http://resources.ovirt.org/repos/ovirt/tested/master/rpm/el7/',
        'ovirt-master-fc24':
            'http://resources.ovirt.org/repos/ovirt/tested/master/rpm/fc24/',
        'ovirt-master-fc25':
            'http://resources.ovirt.org/repos/ovirt/tested/master/rpm/fc25/',
        'ovirt-master-fc26':
            'http://resources.ovirt.org/repos/ovirt/tested/master/rpm/fc26/',
    }
    out = ovirt_tested_as_mirrors('master')
    assert expected == out
