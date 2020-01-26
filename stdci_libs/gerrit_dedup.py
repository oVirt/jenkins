#!/usr/bin/env python
"""gerrit_dedup.py - Helper script for de-duplicating Gerrit users
"""
from __future__ import absolute_import, print_function
from stdci_libs.gerrit import GerritServer
import argparse


def main():
    args = parse_args()
    args.handler(args)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Gerrit account unifying tool'
    )
    parser.add_argument(
        '-s', '--server', default='gerrit.ovirt.org',
        help='Gerrit serer to connect to'
    )
    parser.add_argument(
        '-p', '--port', default=29418,
        help='Port of gerrit server to connect to'
    )
    subparsers = parser.add_subparsers()
    query_parser = subparsers.add_parser(
        'query', help='Query accounts for a given name',
        description='Query accounts for a given name',
    )
    query_parser.set_defaults(handler=query_main)
    query_parser.add_argument('name')
    merge_parser = subparsers.add_parser(
        'merge_onto', help='Merge accounts together',
        description=(
            'Merge one or more account numbers given from the 2nd argument on '
            'into the account given in the 1st argument.'
        ),
    )
    merge_parser.set_defaults(handler=merge_main)
    merge_parser.add_argument('to_keep', type=int)
    merge_parser.add_argument('to_merge', nargs='+', type=int)
    return parser.parse_args()


def query_main(args):
    gerrit = get_gerrit(args)
    output = get_dup_report(gerrit, args.name)
    print(output)


def merge_main(args):
    gerrit = get_gerrit(args)
    for to_merge in args.to_merge:
        merge(gerrit, args.to_keep, to_merge)
    gerrit.run_ssh_command('flush-caches --all')


def merge(gerrit, to_keep, to_merge):
    print("Merging account {0} into {1}".format(to_merge, to_keep))
    print(run_gsql(gerrit, """
        update account_external_ids set account_id={0} where account_id={1};
    """.format(to_keep, to_merge)))
    print(run_gsql(gerrit, """
        update accounts set preferred_email=NULL where account_id={1};
    """.format(to_keep, to_merge)))
    gerrit.run_ssh_command('set-account --inactive {0}'.format(to_merge))


def get_dup_report(gerrit, name):
    return run_gsql(gerrit, """
        select account_id, full_name, preferred_email, registered_on, inactive,
        (select count(1) from account_external_ids e
        where e.account_id = a.account_id) as ex_ids,
        (select count(1) from changes c
        where c.owner_account_id = a.account_id) as changes,
        (select count(1) from change_messages m
        where m.author_id = a.account_id) as comments
        from accounts a
        where full_name like '{}'
        order by registered_on asc;
    """.format(name))


def run_gsql(gerrit, sql):
    out, err = gerrit.run_ssh_command("gsql -c \"{0}\"".format(sql))
    return out


def get_gerrit(args):
    return GerritServer(args.server, args.port, 'SSH')


if __name__ == '__main__':
    main()
