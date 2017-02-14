#!/usr/bin/env python
"""test_mirror_client.py - Tests for mirror_client.py
"""
from textwrap import dedent
from six.moves import StringIO
import pytest
from six.moves.BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import json
from threading import Thread
from six.moves.urllib.parse import urljoin
import requests
from time import sleep
from os import environ

from scripts.mirror_client import (
    inject_yum_mirrors, inject_yum_mirrors_str, mirrors_from_http
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
        """
    ).lstrip()


@pytest.fixture
def mirrors_dict():
    return dict(
        plain_mirrored_repo='http://mirror.com/yum/repo',
        list_mirrored_repo='http://mirror.com/yum/list_repo',
        metalink_mirrored_repo='http://mirror.com/yum/metalink_repo',
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
        proxy = _none_

        [list_mirrored_repo]
        name = A mirrored repo with an (upstream) mirror list
        failovermethod = priority
        baseurl = http://mirror.com/yum/list_repo
        proxy = _none_

        [metalink_mirrored_repo]
        name = A mirrored repo with a metalink configuration
        failovermethod = priority
        baseurl = http://mirror.com/yum/metalink_repo
        proxy = _none_

        [unmirrored_repo]
        name = A non-mirrored repo
        baseurl = http://example.com/yum/another_repo
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

        """
    ).lstrip()


@pytest.yield_fixture
def mirror_server(mirrors_dict):
    mirror_file_path = '/mirrors.json'
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
            else:
                self.send_error(404)

    server_address = ('127.0.0.1', 8765)
    server_url = 'http://{0}:{1}'.format(*server_address)
    server = HTTPServer(server_address, MirrorRequestHandler)
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
                    'http://{0}:8766'.format(server_address[0]),
                    mirror_file_path
                ),
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


def test_mirrors_from_http(mirror_server, mirrors_dict):
    result = mirrors_from_http(
        mirror_server['mirror_url'], mirror_server['json_varname']
    )
    assert result == mirrors_dict
    result = mirrors_from_http(mirror_server['bad_path_url'])
    assert result == {}
    result = mirrors_from_http(mirror_server['bad_port_url'])
    assert result == {}
