from __future__ import print_function
import sys


def pytest_collect_file(path, parent):
    """If the test file we find is in a directory path that contains a
    directory called 'test', check if the same path without the 'test'
    directory exists and if so, add it to the PYTHONPATH
    """
    tfdir = path.dirpath()
    testdir = next(
        (p for p in reversed(tfdir.parts()) if p.basename == 'test'), None
    )
    if not testdir:
        return
    code_relpath = tfdir.relto(testdir)
    code_path = testdir.dirpath() / code_relpath
    if code_path.isdir() \
            and str(code_path).startswith(str(parent.session.fspath)) \
            and str(code_path) not in sys.path:
        sys.path.insert(0, str(code_path))
