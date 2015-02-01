#!/usr/bin/python
"""Alert/Abandon old Gerrit patches
Any patch with no activity for 30 days
send an email to author and cc all parties.
If author not from RedHat, cc iheim@ and
bazulay@.

Any patch with no acticity for 60 days
abandoned with comment "Abandoned due
to no activity - please restore if
still relevant"
"""

from __future__ import print_function
from email.mime.text import MIMEText
import json
import subprocess
import sys
import logging
import traceback
import smtplib
import argparse
import os

CC_EMAIL = "iheim@redhat.com,bazulay@redhat.com"
SSH = "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"


def check_forgotten_patches(days, t_project):
    "Return list of commits inactive for the given days."
    gerrit_call = (
        "%s gerrit query --format=JSON status:open "
        "--dependencies age:%sd project:%s"
        ) % (SSH, days, t_project)
    shell_command = ["bash", "-c", gerrit_call]
    shell_output = log_exec(shell_command)
    f_patches = {}
    for line in shell_output.split('\n'):
        if not line:
            continue
        data = json.loads(line)
        try:
            f_patch = data['number']
            fp_owner = data['owner']
            f_patches[f_patch] = fp_owner
        except KeyError:
            pass
    return f_patches


def abandon_patch(commit):
    "Abandon the patch with comment."
    message = "Abandoned due to no activity - \
            please restore if still relevant"
    gerrit_call = (
        "%s gerrit review --format=JSON "
        "--abandon %s --message %s"
        ) % (SSH, commit, message)
    shell_command = ["bash", "-c", gerrit_call]
    return log_exec(shell_command)


def log_exec(argv, custom_input=None):
    "Execute a given shell command while logging it."
    out = None
    err = None
    rcode = None
    try:
        logging.debug(argv)
        stdin = None
        if custom_input is not None:
            logging.debug(custom_input)
            stdin = subprocess.PIPE
        proc = subprocess.Popen(
            argv, stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        out, err = proc.communicate(custom_input)
        rcode = proc.returncode
        logging.debug(out)
        logging.debug(err)
    except EnvironmentError:
        logging.error(traceback.format_exc())
    if rcode != 0:
        print("Error executing \"%s\"\n" % " ".join(argv))
        print("Output: %s\n" % str(out))
        print("Error: %s\n" % str(err))
        print("Return code: %s\n" % str(rcode))
        sys.exit(2)
    else:
        return out

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "projects", help="List of projects",
        nargs='+')
    parser.add_argument(
        "--server", help="Gerrit server, default: gerrit.ovirt.org",
        default="gerrit.ovirt.org")
    parser.add_argument(
        "--port", help="SSH Port,default: 29418",
        default="29418")
    parser.add_argument(
        "--user", help="SSH User, default: %s" % os.environ["USER"],
        default=os.environ["USER"])
    parser.add_argument("--key", help="SSH Key file path")
    parser.add_argument(
        "--mail", help="Mail server, default: localhost",
        default="localhost")
    parser.add_argument(
        "--cc", help="CC mail id's for non-redhat emails",
        nargs='+')
    parser.add_argument(
            "--warning-days-limit", help="Number of days, default: 30",
            default=30, dest='warning_days')
    parser.add_argument(
            "--abandon-days-limit", help="Number of days, default 60",
            default=60, dest='abandon_days')
    parser.add_argument(
            "--dry-run", help="Show what would have been abandoned",
            action="store_true", dest='dry_run')

    ARGS = parser.parse_args()

    # Construct ssh command based on ssh key file
    if ARGS.key:
        SSH += " -i %s -p %s %s@%s" % (
            ARGS.key, ARGS.port, ARGS.user, ARGS.server)
    else:
        SSH += " -p %s %s@%s" % (ARGS.port, ARGS.user, ARGS.server)

    MAIL_SERVER_HOST = ARGS.mail
    SUBJECT = "Forgotten Patches"
    MAILSERVER = smtplib.SMTP(MAIL_SERVER_HOST)
    FROMADDR = "noreply+patchwatcher@ovirt.org"
    if ARGS.cc:
        CCADDR = ",".join(ARGS.cc)
    else:
        CCADDR = CC_EMAIL

    patches = []
    DAYS = [ARGS.abandon_days, ARGS.warning_days]
    WARN_TEMPLATE = (
        "Your patch did not have any activity for over 30 days, "
        "please consider nudging for more attention."
        ": http://gerrit.ovirt.org/%s")
    ABANDON_TEMPLATE = (
        "Patch http://gerrit.ovirt.org/%s abandoned"
        "due to no activity - please restore if relevant")

    for project in ARGS.projects:
        for day in DAYS:
            output = check_forgotten_patches(day, project)
            if not output:
                print (
                    "No forgotten patches within the last "
                    "%d days were found in project %s"
                    % (day, project))
            for patch, owner in output.items():
                if patch not in patches:
                    patches.append(patch)
                    if day == ARGS.abandon_days:
                        if not ARGS.dry_run:
                            try:
                                abandon_patch(patch)
                                txt = ABANDON_TEMPLATE % patch
                                msg = MIMEText(
                                    'Subject: %s\n\n%s' % (SUBJECT, txt))
                                msg['To'] = owner['email']
                                if "@redhat.com" not in owner['email']:
                                    msg['CC'] = CCADDR
                                MAILSERVER.sendmail(
                                    FROMADDR, owner['email'],
                                    msg.as_string())
                            except EnvironmentError:
                                print("Error abandoning patch %s" % patch)
                        else:
                            print(
                                "Patch %s would have been abandoned"
                                % patch)
                    else:
                        txt = WARN_TEMPLATE % patch
                        msg = MIMEText('Subject: %s\n\n%s' % (SUBJECT, txt))
                        msg['To'] = owner['email']
                        if "@redhat.com" not in owner['email']:
                            msg['CC'] = CCADDR
                        if not ARGS.dry_run:
                            MAILSERVER.sendmail(
                                FROMADDR, owner['email'],
                                msg.as_string())
                        else:
                            print(
                                "%s would have been emailed to nudge patch %s"
                                % (owner['email'], patch))
    MAILSERVER.quit()
