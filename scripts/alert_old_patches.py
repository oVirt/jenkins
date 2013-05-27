#!/usr/bin/python


from __future__ import print_function
import json
import subprocess
import sys
import logging
import traceback
import smtplib


def checkForgottenPatches(gerritURL, days, project):
    gerrit_call = ('ssh -o StrictHostKeyChecking=no -o \
            UserKnownHostsFile=/dev/null -p 29418 %s gerrit \
            query --format=JSON status:open --dependencies \
            age:%sd project:%s' % (gerritURL, days, project))
    shell_command = ["bash", "-c", gerrit_call]
    output, err, rc = _logExec(shell_command)
    if rc != 0:
        print("Something wrong happened!\n" + str(err))
        sys.exit(2)
    patches = {}
    for line in output.split('\n'):
        if not line:
            continue
        data = json.loads(line)
        try:
            patch = data['number']
            owner = data['owner']
            patches[patch] = owner
        except KeyError:
            pass
    return patches


def _logExec(argv, input=None):
    " Execute a given shell command while logging it. "

    out = None
    err = None
    rc = None
    try:
        logging.debug(argv)
        stdin = None
        if input is not None:
            logging.debug(input)
            stdin = subprocess.PIPE
        p = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate(input)
        rc = p.returncode
        logging.debug(out)
        logging.debug(err)
    except:
        logging.error(traceback.format_exc())
    return (out, err, rc)


if __name__ == "__main__":
    subject = "Forgotten Patches"
    mailserver = smtplib.SMTP('localhost')
    project = sys.argv[1]
    fromaddr = "Patchwatcher@ovirt.org"
    patches = []
    mails = [
            (90, 'Your patch did not have any activity for over 90 days, it may be '
                'abandoned automatically by the system in the near future : http://gerrit.ovirt.org/%s.'),
            (60, 'Your patch did not have any activity for over 60 days, please consider '
                'nudging for more attention, or should it be abandoned. : http://gerrit.ovirt.org/%s.'),
            (30, 'Your patch did not have any activity for over 30 days, please consider '
                'nudging for more attention. : http://gerrit.ovirt.org/%s.'),
    ]
    for days, template in mails:
        output = checkForgottenPatches("gerrit.ovirt.org", days, project)
        if not output:
            print("Forgotten patches within the last %d days were not found" %
                  days)
        for patch, owner in output.items():
            if patch not in patches:
                patches.append(patch)
                txt = template % patch
                msg = 'Subject: %s\n\n%s' % (subject, txt)
                mailserver.sendmail(fromaddr, owner['email'], msg)
    mailserver.quit()
