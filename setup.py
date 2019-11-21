"""Setup.py - Python build/installation script for making various tools
generally avilabe in the system. This script is primarily meant alongside
`pipenv` for installing the tools in containers
"""
import setuptools

setuptools.setup(
    name="stdci_tools",
    version="0.0.1",
    author="oVirt CI team",
    author_email="infra@ovirt.org",
    description="oVirt Standard-CI tools",
    long_description=(
        "# oVirt Standard-CI tools\n\n"
        "A set of tools and scripts used by the oVirt Standard-CI system"
    ),
    long_description_content_type="text/markdown",
    packages=['scripts'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
    ],
    install_requires = ["six", "requests", "pyyaml", "jinja2", "pyxdg"],
    entry_points={
        'console_scripts': [
            'usrc = scripts.usrc:main',
            'pusher = scripts.pusher:main',
            'mirror_client = scripts.mirror_client:main',
            'decorate = scripts.decorate:decorate',
        ]
    }
)

