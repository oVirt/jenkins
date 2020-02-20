"""file_utils.py: a library to work with files and directories
"""

from contextlib import contextmanager
import os


@contextmanager
def workdir(path: str):
    """A context manager to change the working directory
    """
    previous_workdir = os.getcwd()
    os.chdir(path)
    try:
        yield os.getcwd()
    finally:
        os.chdir(previous_workdir)
