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
        "%s gerrit query --format=JSON --dependencies "
        "status:open age:%dd project:%s"
        ) % (SSH, days, t_project)
    if ARGS.debug:
        print (gerrit_call)
    shell_command = ["bash", "-c", gerrit_call]
    shell_output = log_exec(shell_command)
    f_patches = {}
    for line in shell_output.split('\n'):
        if not line:
            continue
        data = json.loads(line)
        try:
            fp_patch = data['number']
            fp_email = data['owner']['email']
            if fp_patch and fp_email:
                if fp_email not in f_patches.keys():
                    f_patches[fp_email] = [fp_patch]
                else:
                    f_patches[fp_email].append(fp_patch)
        except KeyError:
            pass
    return f_patches


def abandon_patch(commit, project):
    "Abandon the patch with comment."
    message = "Abandoned due to no activity - \
            please restore if still relevant"
    gerrit_call = (
        "%s gerrit review --project=%s "
        "--message %s --abandon %s"
        ) % (SSH, project, message, commit)
    shell_command = ["bash", "-c", gerrit_call]
    return log_exec(shell_command)


def gen_warning_email_body(day, patches):
    "Generate warning email body from list of patches."
    body = (
        "The following patches did not have any activity for over %d days, "
        "please consider nudging for more attention." % day)
    for patch in patches:
        body += "\nhttp://gerrit.ovirt.org/%s" % patch
    return body


def abandon_patch_and_gen_email_body(day, patches, project):
    "Abandon the patch and generate abandon email body from list of patches"
    body = (
        "The following patches were abandoned "
        "due to no activity for over %d days, "
        "please restore if relevant" % day)
    for patch in patches:
        try:
            abandon_patch(patch, project)
        except EnvironmentError:
            print("Error abandoning patch %s" % patch)
            pass
        body += "\nhttp://gerrit.ovirt.org/%s" % patch
    return body


def dry_run_message_gen(patches):
    "Generate dry run output message from list of patches"
    body = ""
    for patch in patches:
        body += "http://gerrit.ovirt.org/%s\n" % patch
    return body


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
        "--projects", help="Comma separated list of projects",
        metavar="PROJECT1,PROJECT2,..", required=True)
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
        default=30, dest='warning_days', type=int)
    parser.add_argument(
        "--abandon-days-limit", help="Number of days, default 60",
        default=60, dest='abandon_days', type=int)
    parser.add_argument(
        "--dry-run", help="Show what would have been abandoned",
        action="store_true", dest='dry_run')
    parser.add_argument(
        "--debug", help="Print the gerrit commands",
        action="store_true", dest='debug')
    parser.add_argument(
        "--with-email", help="Email address to send the dry run output",
        default=None, dest='with_email')

    ARGS = parser.parse_args()

    # Construct ssh command based on ssh key file
    if ARGS.key:
        SSH += " -i %s -p %s %s@%s" % (
            ARGS.key, ARGS.port, ARGS.user, ARGS.server)
    else:
        SSH += " -p %s %s@%s" % (ARGS.port, ARGS.user, ARGS.server)

    MAIL_SERVER_HOST = ARGS.mail
    SUBJECT = "Forgotten Patches"
    if ARGS.dry_run and not ARGS.with_email:
        MAILSERVER = None
    else:
        MAILSERVER = smtplib.SMTP(MAIL_SERVER_HOST)

    FROMADDR = "noreply+patchwatcher@ovirt.org"
    if ARGS.cc:
        CCADDR = ",".join(ARGS.cc)
    else:
        CCADDR = CC_EMAIL

    DAYS = [int(ARGS.abandon_days), int(ARGS.warning_days)]

    for project in ARGS.projects.split(','):
        for day in DAYS:
            output = check_forgotten_patches(day, project)
            if not output:
                print (
                    "No forgotten patches within the last "
                    "%d days were found in project %s"
                    % (day, project))
            else:
                for email, patches in output.items():
                    if ARGS.dry_run:
                        if day == ARGS.abandon_days:
                            notice_txt = (
                                "The following patches from %s "
                                "would have been abandoned" % email)
                        else:
                            notice_txt = (
                                "%s would have been emailed "
                                "to nudge the following patches" % email)
                        notice = (
                            "%s \n %s" % (
                                notice_txt, dry_run_message_gen(patches)))
                        if ARGS.with_email:
                            msg = MIMEText(notice)
                            msg['Subject'] = SUBJECT
                            msg['To'] = ARGS.with_email
                            msg['From'] = FROMADDR
                            MAILSERVER.sendmail(
                                    FROMADDR, ARGS.with_email,
                                    msg.as_string())
                        else:
                            print(notice)
                    else:
                        if day == ARGS.abandon_days:
                            txt = abandon_patch_and_gen_email_body(
                                    day, patches, project)
                        else:
                            txt = gen_warning_email_body(day, patches)
                        msg = MIMEText(txt)
                        msg['Subject'] = SUBJECT
                        msg['To'] = email
                        msg['From'] = FROMADDR
                        if "@redhat.com" not in email:
                            msg['CC'] = CCADDR
                            email += "," + CCADDR
                        MAILSERVER.sendmail(
                            FROMADDR, [email],
                            msg.as_string())

    if MAILSERVER:
        MAILSERVER.quit()
