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
    obj_array = []
    patch_array = []
    patch_list = {}
    for line in output.split('\n'):
        if not line:
            continue
        myobject = json.loads(line)
        obj_array.append(myobject)
    for i in obj_array:
        for k in i.keys():
            if "number" == k:
                patch = i[k]
            if "owner" == k:
                owner = i[k]
                email = i[k]["email"]
                patch_list[patch] = owner
    return patch_list


def _logExec(argv, input=None):
#This function executes a given shell command while logging it.

    out = None
    err = None
    rc = None
    try:
        logging.debug(argv)
        stdin = None
        if input is not None:
            logging.debug(input)
            stdin = subprocess.PIPE
        p = subprocess.Popen(argv, stdin=stdin, \
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(input)
        rc = p.returncode
        logging.debug(out)
        logging.debug(err)
    except:
        logging.error(traceback.format_exc())
    return (out, err, rc)


if __name__ == "__main__":
    patchlist = []
    subject = "Forgotten Patches"
    mailserver = smtplib.SMTP('localhost')
    project = sys.argv[1]
    fromaddr = "Patchwatcher@ovirt.org"
    output = checkForgottenPatches("gerrit.ovirt.org", 30, project)
    if not output:
        print("Forgotten patches within the last 7 days were not found")
        sys.exit(0)
    for i, k in output.items():
        txt = 'your patch did not have any activity for over 30 days, please consider ' \
              'nudging for more attention. : http://gerrit.ovirt.org/%s ' % i
        msg = 'Subject: %s\n\n%s' %(subject, txt)
        patchlist.append(i)
        toaddr = k["email"]
        mailserver.sendmail(fromaddr, toaddr, msg)

    output = checkForgottenPatches("gerrit.ovirt.org", 60, project)
    if not output:
        print("Forgotten patches within the last 60 days were not found")
        sys.exit(0)
    for i, k in output.items():
        txt = 'your patch did not have any activity for over 60 days, please consider ' \
              'nudging for more attention, or should it be abandoned : http://gerrit.ovirt.org/%s ' % i
        msg = 'Subject: %s\n\n%s' %(subject, txt)
        toaddr = k["email"]
        if i not in patchlist:
            patchlist.append(i)
            mailserver.sendmail(fromaddr, toaddr, msg)

    output = checkForgottenPatches("gerrit.ovirt.org", 90, project)
    if not output:
        print("Forgotten patches within the last 7 days were not found")
        sys.exit(0)
    for i, k in output.items():
        txt = 'your patch did not have any activity for over 90 days, it may be ' \
              'abandoned automatically by the system in the near future : http://gerrit.ovirt.org/%s  ' % i
        msg = 'Subject: %s\n\n%s' %(subject, txt)
        toaddr = k["email"]
        if i not in patchlist:
            patchlist.append(i)
            mailserver.sendmail(fromaddr, toaddr, msg)
    mailserver.quit
    sys.exit(1)
