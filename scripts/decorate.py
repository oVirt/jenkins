"""decorate.py - Workload decoration script

This scripts uses the STDCI tooling top perform various actions that help
running CI workloads such as source code cloning and mirror injection.
This script is meant to to be used in a initContainer for a POD that will run
a CI workload
"""
import os
import sys
import stat
from argparse import Namespace
from pathlib import Path
import logging

from scripts.git_utils import git
from scripts.stdci_logging import setup_console_logging
from scripts import usrc
from scripts.mirror_client import mirrors_from_uri, inject_yum_mirrors_file

EXPORTED_ARTIFACTS = "exported-artifacts"
EXTRA_SOURCES = 'extra_sources'
MIRRORS_YAML = 'mirrors.yaml'


logger = logging.getLogger(__name__)

def decorate():
    setup_logging()
    clone_source_code()
    inject_extra_sources()
    script = ensure_executable_script()
    if script is None:
        return
    inject_mirrors(script)

def setup_logging():
    settings = Namespace(debug=True, log=sys.stderr)
    setup_console_logging(settings)

def clone_source_code():
    logger.info('Cloning source code')
    git('init', '.')
    git(
        'fetch', '--tags', os.environ["STD_CI_CLONE_URL"],
        '+refs/heads/*:refs/remotes/origin/*'
    )
    git(
        'fetch', '--tags', os.environ["STD_CI_CLONE_URL"],
        '+' + os.environ["STD_CI_REFSPEC"] + ':myhead'
    )
    git('checkout', 'myhead')
    usrc_get()

def usrc_get():
    logger.info('Fetching upstream source')
    sys.argv = [usrc.__name__, 'get']
    try:
        usrc.main()
    except SystemExit as e:
        if e.code != 0:
            raise RuntimeError(f'{usrc.__name__} exited with error: {e.code}')

def ensure_executable_script():
    script = os.environ.get('STD_CI_SCRIPT')
    if not script:
        logger.info('STDCI script not specified')
        return None
    if not os.path.exists(script):
        logger.info('Given STDCI script does not exist')
        return None
    logger.info('Ensuring STDCI script is executable')
    os.chmod(script, stat.S_IRWXG|stat.S_IRWXU)
    return Path(script)

def inject_extra_sources():
    exported_artifacts = find_exported_artifacts()
    extra_sources = exported_artifacts / EXTRA_SOURCES
    if not extra_sources.exists():
        logger.info('extra_sources file not found')
        return
    logger.info('Found extra_sources file')
    target = Path(EXTRA_SOURCES)
    target.write_bytes(extra_sources.read_bytes())

def inject_mirrors(script):
    distro = os.environ['STD_CI_DISTRO']
    exported_artifacts = find_exported_artifacts()
    mirrors_yaml = exported_artifacts / MIRRORS_YAML
    if not mirrors_yaml.exists():
        logger.info('`mirros.yaml` file not found')
        return
    mirrors = None
    results_path = exported_artifacts / 'yumrepos'
    for fil in script.parent.iterdir():
        if not fil.name.startswith(f'{script.stem}.'):
            continue
        if not (
            fil.name.endswith('.yumrepos') or
            fil.name.endswith(f'.yumrepos.{distro}')
        ):
            continue
        if mirrors is None:
            mirrors = mirrors_from_uri(str(mirrors_yaml))
        inject_yum_mirrors_file(mirrors, str(fil))
        results_path.mkdir(parents=True, exist_ok=True)
        (results_path/fil.name).write_bytes(fil.read_bytes())

def find_exported_artifacts():
    return Path(os.environ.get('EXPORTED_ARTIFACTS', f'/{EXPORTED_ARTIFACTS}'))
