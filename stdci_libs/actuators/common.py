"""Tools for writing actuators"""

from click import argument


"""A path to a push map file"""
push_map_arg = argument('push-map', envvar='PUSHER_PUSH_MAP', type=str)


"""A destination branch for pushing patches"""
target_branch_arg = argument(
    'target-branch', envvar='REPO_PUSH_BRANCH', type=str
)

"""A git refspec to check out"""
refspec_arg = argument('refspec', envvar='REPO_REF', type=str)


"""A git repository to clone"""
repo_url_arg = argument('repo-url', envvar='REPO_URL', type=str)
