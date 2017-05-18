#!/usr/bin/env python
"""change_queue.changes - Change objects for use with change_queue classes
"""
from jinja2 import Environment, PackageLoader
import email
from six import string_types
from collections import Iterable, namedtuple
import smtplib
import re
from textwrap import wrap
from threading import Lock

from scripts.object_utils import object_witp_opt_attrs, object_proxy
from scripts.gerrit import GerritPatchset
from scripts.jenkins_objects import BuildsList


class DisplayableChange(object_witp_opt_attrs):
    """Base/Mixin class that ensures a change has the attributes that allow it
    to be displayed to users
    """
    @property
    def default_id(self):
        return self

    @property
    def default_presentable_id(self):
        return self.id

    def _cast_presentable_id(self, value):
        return str(value)

    default_url = None


class DisplayableChangeWrapper(DisplayableChange, object_proxy):
    """Wrapper class to make non-displayable change objects look like
    displayable ones
    """


class ChangeInStream(object_witp_opt_attrs):
    """Base/Mixin class that ensure an object has the attributes that allow it
    to be used as a chage object with the ChangeQueueWithStreams class
    """
    default_stream_id = None


class ChangeInStreamWrapper(ChangeInStream, object_proxy):
    """Wrapper class to make non in-stream changes not fail code attempting to
    get stream information
    """


class EmailNotifyingChange(DisplayableChange):
    """Base/Mixin class for changes that can send email notifications on queue
    events

    Objects with this mixing can optionally have the following attributes set
    on them to determine which messages are sent and to whom:
    - recipients:            Iterable of email addresses to send notifications
                             to if not overridden by event-specific attribute
    - originator:            An email address (string) from which notifications
                             are sent if not overridden by event-specific
                             attribute
    - added_recipients:      Iterable of email addresses to send notifications
                             to when the change was successfully added to the
                             queue
    - added_originator:      An email address (string) from which notifications
                             are sent when the change was successfully added to
                             the queue
    - rejected_recipients:   Iterable of email addresses to send notifications
                             to when the change could not be added to the queue
                             due to dependency issues
    - rejected_originator:   An email address (string) from which notifications
                             are sent when the change could not be added to the
                             queue due to dependency issues
    - successful_recipients: Iterable of email addresses to send notifications
                             to when the change was successfully tested
    - successful_originator: An email address (string) from which notifications
                             are sent when the change was successfully tested
    - failed_recipients:     Iterable of email addresses to send notifications
                             to when the change was detected as causing test
                             failures or depending on a change that causes
                             failures
    - failed_originator:     An email address (string) from which notifications
                             are sent when the change was detected as causing
                             test failures or depending on a change that causes
                             failures
    - smtp_host:             The host through which notifications will be sent

    All optional attributes have sane defaults that can be seen in the code
    below.
    The 'recipients' attributes can be set to an empty Iterable to indicate
    that a notification should not be sent.
    """
    default_recipients = ('infra@ovirt.org',)
    default_originator = 'oVirt Jenkins <jenkins@ovirt.org>'
    default_smtp_host = 'localhost'

    @staticmethod
    def _to_tuple(value):
        if isinstance(value, Iterable) and not isinstance(value, string_types):
            return tuple(value)
        elif value is None:
            return ()
        else:
            return (value,)

    def _cast_recipients(self, value):
        return self._to_tuple(value)

    @property
    def default_added_originator(self):
        return self.originator

    @property
    def default_added_recipients(self):
        return self.recipients

    def _cast_added_recipients(self, value):
        return self._to_tuple(value)

    @property
    def default_rejected_originator(self):
        return self.originator

    @property
    def default_rejected_recipients(self):
        return self.recipients

    def _cast_rejected_recipients(self, value):
        return self._to_tuple(value)

    @property
    def default_successful_originator(self):
        return self.originator

    @property
    def default_successful_recipients(self):
        return self.recipients

    def _cast_successful_recipients(self, value):
        return self._to_tuple(value)

    @property
    def default_failed_originator(self):
        return self.originator

    @property
    def default_failed_recipients(self):
        return self.recipients

    def _cast_failed_recipients(self, value):
        return self._to_tuple(value)

    @classmethod
    def _get_jinja_env(cls):
        if not hasattr(cls, '_jinja_env'):
            cls._jinja_env = Environment(loader=PackageLoader(__name__))

            def wordwrap(s, width=79):
                return '\n'.join(wrap(s, width))
            # Replace jinja broken word wrap with something that works
            cls._jinja_env.filters['wordwrap'] = wordwrap
        return cls._jinja_env

    def _get_status_message_text(
        self, status, qname, cause, test_url, recipients, originator
    ):
        env = self._get_jinja_env()
        tmpl = env.get_template(status + '-email.txt.j2')
        return tmpl.render(
            change=self, qname=qname,
            cause=DisplayableChangeWrapper(cause), test_url=test_url,
            recipients=recipients, originator=originator,
        )

    def _get_status_message(self, status, qname, cause, test_url):
        recipients = getattr(self, status + '_recipients')
        if not recipients:
            return None
        originator = getattr(self, status + '_originator')
        msg = email.message_from_string(self._get_status_message_text(
            status, qname, cause, test_url, recipients, originator)
        )
        if 'To' not in msg:
            msg['To'] = ', '.join(recipients)
        if 'From' not in msg:
            msg['From'] = originator
        return msg

    # report_status might be called by multiple threads, so we need to lock the
    # unsafe parts
    _report_status_lock = Lock()

    def report_status(self, status, qname, cause, test_url=None, lock=None):
        """Sends an email to report about the change status

        :param str status:   The reported status ('added', 'rejected',
                             'successful' or 'failed')
        :param str qname:    The name of the queue that change was managed in
        :param object cause: If diagnosed, the change object that caused this
                             change to be removed from the queue (on test
                             failure or rejection). May be None or even this
                             change itself
        :param str test_url: The url of a failed or a successful test that is
                             the cause for the change status report. May be
                             none for statuses that do not follow a test run
                             (e.g. 'added' or 'rejected')
        :param Lock lock:    (Optional) A lock object to lock critical sections
                             in this method is invoked from multiple threads

        This method may be called in parallel on different changes by multiple
        thread, so it can be passed a lock to allow it to lock execution for
        all other calls to this method. Be default the lock will only work at
        the class level, so calling code that may call this method on different
        classes needs to pass in its own lock.
        """
        if lock is None:
            lock = self._report_status_lock
        with lock:
            msg = self._get_status_message(status, qname, cause, test_url)
            if msg is None:
                return
            smtp_host = getattr(self, 'smtp_host')
        smtp = None
        try:
            smtp = smtplib.SMTP(smtp_host)
            smtp.sendmail(msg['From'], re.split(',\s*', msg['To']), str(msg))
        finally:
            if smtp is not None:
                smtp.quit()


class NumberChange(EmailNotifyingChange, namedtuple('_NumberChange', (
    'id', 'number', 'recipients'
))):
    """Dummy change class that just contains numbers. It is mostly for testing
    purposes
    """
    @property
    def presentable_id(self):
        return '{id} [{number}]'.format(id=self.id, number=self.number)


class ChangeWithBuilds(object_witp_opt_attrs):
    """Base/Mixin class for change objects that track build jobs to get built
    artifacts

    Builds are specified as a BuildsList object
    """
    default_builds = BuildsList()

    def set_builds_from_env(self, env_var='BUILDS_LIST'):
        self.builds = BuildsList.from_env_json(env_var)


class ChangeWithBuildsWrapper(ChangeWithBuilds, object_proxy):
    """Wrapper class to make changes appear like they have builds"""


class GerritMergedChange(ChangeWithBuilds):
    """A change class for changes that get created as a result of merging
    patches to Gerrit repos

    Merged patches are members of a change stream that is identified by the
    same project and branche (As well as server and port in case multiple
    Gerrit servers are used)
    """
    def __init__(self, gerrit_patchset):
        self._gerrit_patchset = gerrit_patchset

    @property
    def gerrit_patchset(self):
        return self._gerrit_patchset

    @classmethod
    def from_jenkins_env(cls):
        o = cls(gerrit_patchset=GerritPatchset.from_jenkins_env())
        o.set_builds_from_env()
        return o

    @property
    def id(self):
        return (
            self.gerrit_patchset.server.host,
            self.gerrit_patchset.server.port,
            self.gerrit_patchset.change.number,
            self.gerrit_patchset.patchset_number,
        )

    @property
    def presentable_id(self):
        return '{0},{1} ({2})'.format(
            self.gerrit_patchset.change.number,
            self.gerrit_patchset.patchset_number,
            self.gerrit_patchset.project.name,
        )

    @property
    def url(self):
        # The change url Gerrit gives us is not good enough for looking into
        # individual patchsets, so we need to fix it
        ch_nstr = str(self.gerrit_patchset.change.number)
        ch_url = self.gerrit_patchset.change.url
        ch_psnstr = str(self.gerrit_patchset.patchset_number)
        if ch_url.endswith('/' + ch_nstr):
            real_ch_url = \
                '{0}/#/c/{1}'.format(ch_url[:-len(ch_nstr) - 1], ch_nstr)
        else:
            real_ch_url = ch_url
        return '/'.join((real_ch_url, ch_psnstr))

    @property
    def stream_id(self):
        return (
            self.gerrit_patchset.server.host,
            self.gerrit_patchset.server.port,
            self.gerrit_patchset.project.name,
            self.gerrit_patchset.branch.name,
        )
