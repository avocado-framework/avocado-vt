"""
Utility classes and functions to handle connection to a libvirt host system

The entire contents of callables in this module (minus the names defined in
NOCLOSE below), will become methods of the Virsh and VirshPersistent classes.
A Closure class is used to wrap the module functions, lambda does not
properly store instance state in this implementation.

Because none of the methods have a 'self' parameter defined, the classes
are defined to be dict-like, and get passed in to the methods as a the
special ``**dargs`` parameter.  All virsh module functions _MUST_ include a
special ``**dargs`` (variable keyword arguments) to accept non-default
keyword arguments.

The standard set of keyword arguments to all functions/modules is declared
in the VirshBase class.  Only the 'virsh_exec' key is guaranteed to always
be present, the remainder may or may not be provided.  Therefor, virsh
functions/methods should use the dict.get() method to retrieve with a default
for non-existant keys.

:copyright: 2012 Red Hat Inc.
"""

import signal
import logging
import os
import re
import weakref
import time
import select
import locale
import base64
import inspect
import platform

from functools import wraps

import aexpect
from aexpect import remote

from avocado.utils import path
from avocado.utils import process

from six.moves import urllib

from virttest import propcan
from virttest import utils_misc
from virttest import data_dir


LOG = logging.getLogger('avocado.' + __name__)

# list of symbol names NOT to wrap as Virsh class methods
# Everything else from globals() will become a method of Virsh class
NOCLOSE = list(globals().keys()) + [
    'NOCLOSE', 'SCREENSHOT_ERROR_COUNT', 'VIRSH_COMMAND_CACHE',
    'VIRSH_EXEC', 'VirshBase', 'VirshClosure', 'VirshSession', 'Virsh',
    'VirshPersistent', 'VirshConnectBack', 'VIRSH_COMMAND_GROUP_CACHE',
    'VIRSH_COMMAND_GROUP_CACHE_NO_DETAIL',
]

# Needs to be in-scope for Virsh* class screenshot method and module function
SCREENSHOT_ERROR_COUNT = 0

# Cache of virsh commands, used by help_command_group() and help_command_only()
# TODO: Make the cache into a class attribute on VirshBase class.
VIRSH_COMMAND_CACHE = None
VIRSH_COMMAND_GROUP_CACHE = None
VIRSH_COMMAND_GROUP_CACHE_NO_DETAIL = False

# This is used both inside and outside classes
try:
    VIRSH_EXEC = path.find_command("virsh")
except path.CmdNotFoundError:
    logging.getLogger('avocado.app').warning(
        "Virsh executable not set or found on path, virsh module will not "
        "function normally")
    VIRSH_EXEC = '/bin/true'


class VirshBase(propcan.PropCanBase):

    """
    Base Class storing libvirt Connection & state to a host
    """

    __slots__ = ('uri', 'ignore_status', 'debug', 'virsh_exec', 'readonly')

    def __init__(self, *args, **dargs):
        """
        Initialize instance with virsh_exec always set to something
        """
        init_dict = dict(*args, **dargs)
        init_dict['virsh_exec'] = init_dict.get('virsh_exec', VIRSH_EXEC)
        init_dict['uri'] = init_dict.get('uri', None)
        init_dict['debug'] = init_dict.get('debug', False)
        init_dict['ignore_status'] = init_dict.get('ignore_status', False)
        init_dict['readonly'] = init_dict.get('readonly', False)
        super(VirshBase, self).__init__(init_dict)

    def get_uri(self):
        """
        Accessor method for 'uri' property that must exist
        """
        # self.get() would call get_uri() recursively
        try:
            return self.__dict_get__('uri')
        except KeyError:
            return None


class VirshSession(aexpect.ShellSession):

    """
    A virsh shell session, used with Virsh instances.
    """

    # No way to get virsh sub-command "exit" status
    # Check output against list of known error-status strings
    ERROR_REGEX_LIST = ['error:\s*.+$', '.*failed.*']

    def __init__(self, virsh_exec=None, uri=None, a_id=None,
                 prompt=r"virsh\s*[\#\>]\s*", remote_ip=None,
                 remote_user=None, remote_pwd=None,
                 ssh_remote_auth=False, readonly=False,
                 unprivileged_user=None,
                 auto_close=False, check_libvirtd=True):
        """
        Initialize virsh session server, or client if id set.

        :param virsh_exec: path to virsh executable
        :param uri: uri of libvirt instance to connect to
        :param id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param prompt: Regular expression describing the shell's prompt line.
        :param remote_ip: Hostname/IP of remote system to ssh into (if any)
        :param remote_user: Username to ssh in as (if any)
        :param remote_pwd: Password to use, or None for host/pubkey
        :param auto_close: Param to init ShellSession.
        :param ssh_remote_auth: ssh to remote first.(VirshConnectBack).
                                Then execute virsh commands.

        Because the VirshSession is designed for class VirshPersistent, so
        the default value of auto_close is False, and we manage the reference
        to VirshSession in VirshPersistent manually with counter_increase and
        counter_decrease. If you really want to use it directly over VirshPe-
        rsistent, please init it with auto_close=True, then the session will
        be closed in __del__.

            * session = VirshSession(virsh.VIRSH_EXEC, auto_close=True)
        """

        self.uri = uri
        self.remote_ip = remote_ip
        self.remote_user = remote_user
        self.remote_pwd = remote_pwd

        # Special handling if setting up a remote session
        if ssh_remote_auth:  # remote to remote
            if remote_pwd:
                pref_auth = "-o PreferredAuthentications=password"
            else:
                pref_auth = "-o PreferredAuthentications=hostbased,publickey"
            # ssh_cmd is not None flags this as remote session
            ssh_cmd = ("ssh -o UserKnownHostsFile=/dev/null %s -p %s %s@%s"
                       % (pref_auth, 22, self.remote_user, self.remote_ip))
            if uri:
                self.virsh_exec = ("%s \"%s -c '%s'\""
                                   % (ssh_cmd, virsh_exec, self.uri))
            else:
                self.virsh_exec = ("%s \"%s\"" % (ssh_cmd, virsh_exec))
        else:  # setting up a local session or re-using a session
            self.virsh_exec = virsh_exec
            if self.uri:
                self.virsh_exec += " -c '%s'" % self.uri
            ssh_cmd = None  # flags not-remote session

        if readonly:
            self.virsh_exec += " -r"

        if unprivileged_user:
            self.virsh_exec = "su - %s -c '%s'" % (unprivileged_user,
                                                   self.virsh_exec)

        # aexpect tries to auto close session because no clients connected yet
        aexpect.ShellSession.__init__(self, self.virsh_exec, a_id,
                                      prompt=prompt, auto_close=auto_close)

        # Handle remote session prompts:
        # 1.remote to remote with ssh
        # 2.local to remote with "virsh -c uri"
        if ssh_remote_auth or self.uri:
            # Handle ssh / password prompts
            remote.handle_prompts(self, self.remote_user, self.remote_pwd,
                                  prompt, debug=True)

        # fail if libvirtd is not running
        if check_libvirtd:
            if self.cmd_status('list', timeout=60) != 0:
                LOG.debug("Persistent virsh session is not responding, "
                          "libvirtd may be dead.")
                self.auto_close = True
                raise aexpect.ShellStatusError(virsh_exec, 'list')

    def cmd_status_output(self, cmd, timeout=60, internal_timeout=None,
                          print_func=None, safe=False):
        """
        Send a virsh command and return its exit status and output.

        :param cmd: virsh command to send (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param safe: Whether using safe mode when execute cmd.
                In serial sessions, frequently the kernel might print debug or
                error messages that make read_up_to_prompt to timeout. Let's
                try to be a little more robust and send a carriage return, to
                see if we can get to the prompt when safe=True.

        :return: A tuple (status, output) where status is the exit status and
                output is the output of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellStatusError: Raised if the exit status cannot be obtained
        :raise ShellError: Raised if an unknown error occurs
        """
        out = self.cmd_output(cmd, timeout, internal_timeout, print_func, safe)
        for line in out.splitlines():
            if self.match_patterns(line, self.ERROR_REGEX_LIST) is not None:
                return 1, out
        return 0, out

    def cmd_result(self, cmd, ignore_status=False, debug=False, timeout=60):
        """Mimic process.run()"""
        exit_status, stdout = self.cmd_status_output(cmd, timeout=timeout)
        stderr = ''  # no way to retrieve this separately
        result = process.CmdResult(cmd, stdout, stderr, exit_status)

        result.stdout = result.stdout_text
        result.stderr = result.stderr_text
        if not ignore_status and exit_status:
            raise process.CmdError(cmd, result,
                                   "Virsh Command returned non-zero exit status")
        if debug:
            LOG.debug(result)
        return result

    def read_until_output_matches(self, patterns, filter_func=lambda x: x,
                                  timeout=60, internal_timeout=None,
                                  print_func=None, match_func=None):
        """
        Read from child using read_nonblocking until a pattern matches.

        Read using read_nonblocking until a match is found using match_patterns,
        or until timeout expires. Before attempting to search for a match, the
        data is filtered using the filter_func function provided.

        :param patterns: List of strings (regular expression patterns)
        :param filter_func: Function to apply to the data read from the child before
                attempting to match it against the patterns (should take and
                return a string)
        :param timeout: The duration (in seconds) to wait until a match is
                found
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param match_func: Function to compare the output and patterns.
        :return: Tuple containing the match index and the data read so far
        :raise ExpectTimeoutError: Raised if timeout expires
        :raise ExpectProcessTerminatedError: Raised if the child process
                terminates while waiting for output
        :raise ExpectError: Raised if an unknown error occurs
        """
        if not match_func:
            match_func = self.match_patterns
        fd = self._get_fd("expect")
        o = ""
        end_time = time.time() + timeout
        while True:
            try:
                r, w, x = select.select([fd], [], [],
                                        max(0, end_time - time.time()))
            except (select.error, TypeError):
                break
            if not r:
                raise aexpect.ExpectTimeoutError(patterns, o)
            # Read data from child
            data = self.read_nonblocking(internal_timeout,
                                         end_time - time.time())
            if not data:
                break
            # Print it if necessary
            if print_func:
                for line in data.splitlines():
                    print_func(line)
            # Look for patterns
            o += data

            out = ''
            match = match_func(filter_func(o), patterns)
            if match is not None:
                output = o.splitlines()
                # Find the second match in output reverse list, only return
                # the content between the last match and the second last match.
                # read_nonblocking might include output of last command or help
                # info when session initiated,
                # e.g.
                # When use VirshPersistent initiate a virsh session, an list
                # command is send in to test libvirtd status, and the first
                # command output will be like:
                # Welcome to virsh, the virtualization interactive terminal.
                #
                # Type:  'help' for help with commands
                #       'quit' to quit
                #
                # virsh #  Id    Name                           State
                # ----------------------------------------------------
                #
                # virsh #
                # the session help info is included, and the exact output
                # should be the content start after first virsh # prompt.
                # The list command did no harm here with help info included,
                # but sometime other commands get list command output included,
                # e.g.
                #  Running virsh command: net-list --all
                #  Sending command: net-list --all
                #  Id    Name                           State
                #  ----------------------------------------------------
                #
                # virsh #  Name            State      Autostart     Persistent
                #  ----------------------------------------------------------
                #  default              active     yes           yes
                #
                # virsh #
                # The list command output is mixed in the net-list command
                # output, this will fail to extract network name if use set
                # number 2 in list of output splitlines like in function
                # virsh.net_state_dict.
                for i in reversed(list(range(len(output) - 1))):
                    if match_func(output[i].strip(), patterns) is not None:
                        if re.split(patterns[match], output[i])[-1]:
                            output[i] = re.split(patterns[match],
                                                 output[i])[-1]
                            output_slice = output[i:]
                        else:
                            output_slice = output[i + 1:]
                        for j in range(len(output_slice) - 1):
                            output_slice[j] = output_slice[j] + '\n'
                        for k in range(len(output_slice)):
                            out += output_slice[k]
                        return match, out
                return match, o

        # Check if the child has terminated
        if utils_misc.wait_for(lambda: not self.is_alive(), 5, 0, 0.1):
            raise aexpect.ExpectProcessTerminatedError(patterns,
                                                       self.get_status(), o)
        else:
            # This shouldn't happen
            raise aexpect.ExpectError(patterns, o)


# Work around for inconsistent builtin closure local reference problem
# across different versions of python
class VirshClosure(object):

    """
    Callable with weak ref. to override ``**dargs`` when calling reference_function
    """

    def __init__(self, reference_function, dict_like_instance):
        """
        Callable reference_function with weak ref dict_like_instance
        """
        if not issubclass(dict_like_instance.__class__, dict):
            raise ValueError("dict_like_instance %s must be dict or subclass"
                             % dict_like_instance.__class__.__name__)
        self.reference_function = reference_function
        self.dict_like_weakref = weakref.ref(dict_like_instance)

    def __call__(self, *args, **dargs):
        """
        Call reference_function with dict_like_instance augmented by **dargs

        :param args: Passthrough to reference_function
        :param dargs: Updates dict_like_instance copy before call
        """
        new_dargs = self.dict_like_weakref()
        if new_dargs is None:
            new_dargs = {}
        for key in list(new_dargs.keys()):
            if key not in list(dargs.keys()):
                dargs[key] = new_dargs[key]
        return self.reference_function(*args, **dargs)


class Virsh(VirshBase):

    """
    Execute libvirt operations, using a new virsh shell each time.
    """

    __slots__ = []

    def __init__(self, *args, **dargs):
        """
        Initialize Virsh instance with persistent options

        :param args: Initial property keys/values
        :param dargs: Initial property keys/values
        """
        super(Virsh, self).__init__(*args, **dargs)
        # Define the instance callables from the contents of this module
        # to avoid using class methods and hand-written aliases
        globals_tmp = globals().copy()
        for sym, ref in globals_tmp.items():
            if sym not in NOCLOSE and callable(ref):
                # Adding methods, not properties, so avoid special __slots__
                # handling.  __getattribute__ will still find these.
                self.__super_set__(sym, VirshClosure(ref, self))


class VirshPersistent(Virsh):

    """
    Execute libvirt operations using persistent virsh session.
    """

    __slots__ = ('session_id', 'remote_pwd', 'remote_user', 'uri',
                 'remote_ip', 'ssh_remote_auth', 'unprivileged_user',
                 'readonly')

    # B/c the auto_close of VirshSession is False, we
    # need to manage the ref-count of it manually.
    COUNTERS = {}

    def __init__(self, *args, **dargs):
        super(VirshPersistent, self).__init__(*args, **dargs)
        if self.get('session_id') is None:
            # set_uri does not call when INITIALIZED = False
            # and no session_id passed to super __init__
            self.new_session()
        # increase the counter of session_id in COUNTERS.
        self.counter_increase()

    def __del__(self):
        """
        Clean up any leftover sessions
        """
        self.close_session()

    def counter_increase(self):
        """
        Method to increase the counter to self.a_id in COUNTERS.
        """
        session_id = self.__dict_get__("session_id")
        try:
            counter = self.__class__.COUNTERS[session_id]
        except KeyError as e:
            VirshPersistent.COUNTERS[session_id] = 1
            return
        # increase the counter of session_id.
        VirshPersistent.COUNTERS[session_id] += 1

    def counter_decrease(self):
        """
        Method to decrease the counter to self.a_id in COUNTERS.
        If the counter is less than 1, it means there is no more
        VirshSession instance referring to the session. So close
        this session, and return True.
        Else, decrease the counter in COUNTERS and return False.
        """
        session_id = self.__dict_get__("session_id")
        self.__class__.COUNTERS[session_id] -= 1
        counter = self.__class__.COUNTERS[session_id]
        if counter <= 0:
            # The last reference to this session. Closing it.
            session = VirshSession(a_id=session_id)
            # try nicely first
            session.close()
            if session.is_alive():
                # Be mean, in case it's hung
                session.close(sig=signal.SIGTERM)
            del self.__class__.COUNTERS[session_id]
            return True
        else:
            return False

    def close_session(self):
        """
        If a persistent session exists, close it down.
        """
        try:
            session_id = self.__dict_get__('session_id')
            if session_id:
                try:
                    existing = VirshSession(a_id=session_id)
                    if existing.is_alive():
                        self.counter_decrease()
                except (aexpect.ShellStatusError,
                        aexpect.ShellProcessTerminatedError):
                    # session was already closed
                    pass  # don't check is_alive or update counter
                self.__dict_del__("session_id")
        except KeyError:
            # Allow other exceptions to be raised
            pass  # session was closed already

    def new_session(self):
        """
        Open new session, closing any existing
        """
        # Accessors may call this method, avoid recursion
        # Must exist, can't be None
        virsh_exec = self.__dict_get__('virsh_exec')
        uri = self.__dict_get__('uri')  # Must exist, can be None
        readonly = self.__dict_get__('readonly')
        try:
            remote_user = self.__dict_get__('remote_user')
        except KeyError:
            remote_user = "root"
        try:
            remote_pwd = self.__dict_get__('remote_pwd')
        except KeyError:
            remote_pwd = None
        try:
            remote_ip = self.__dict_get__('remote_ip')
        except KeyError:
            remote_ip = None
        try:
            ssh_remote_auth = self.__dict_get__('ssh_remote_auth')
        except KeyError:
            ssh_remote_auth = False
        try:
            unprivileged_user = self.__dict_get__('unprivileged_user')
        except KeyError:
            unprivileged_user = None

        self.close_session()
        # Always create new session
        new_session = VirshSession(virsh_exec, uri, a_id=None,
                                   remote_ip=remote_ip,
                                   remote_user=remote_user,
                                   remote_pwd=remote_pwd,
                                   ssh_remote_auth=ssh_remote_auth,
                                   unprivileged_user=unprivileged_user,
                                   readonly=readonly)
        session_id = new_session.get_id()
        self.__dict_set__('session_id', session_id)

    def set_uri(self, uri):
        """
        Accessor method for 'uri' property, create new session on change
        """
        if not self.INITIALIZED:
            # Allow __init__ to call new_session
            self.__dict_set__('uri', uri)
        else:
            # If the uri is changing
            if self.__dict_get__('uri') != uri:
                self.__dict_set__('uri', uri)
                self.new_session()
            # otherwise do nothing


class VirshConnectBack(VirshPersistent):

    """
    Persistent virsh session connected back from a remote host
    """

    __slots__ = ('remote_ip', )

    def new_session(self):
        """
        Open new remote session, closing any existing
        """

        # Accessors may call this method, avoid recursion
        # Must exist, can't be None
        virsh_exec = self.__dict_get__('virsh_exec')
        uri = self.__dict_get__('uri')  # Must exist, can be None
        remote_ip = self.__dict_get__('remote_ip')
        try:
            remote_user = self.__dict_get__('remote_user')
        except KeyError:
            remote_user = 'root'
        try:
            remote_pwd = self.__dict_get__('remote_pwd')
        except KeyError:
            remote_pwd = None
        super(VirshConnectBack, self).close_session()
        new_session = VirshSession(virsh_exec, uri, a_id=None,
                                   remote_ip=remote_ip,
                                   remote_user=remote_user,
                                   remote_pwd=remote_pwd,
                                   ssh_remote_auth=True)
        session_id = new_session.get_id()
        self.__dict_set__('session_id', session_id)

    @staticmethod
    def kosher_args(remote_ip, uri):
        """
        Convenience static method to help validate argument sanity before use

        :param remote_ip: ip/hostname of remote libvirt helper-system
        :param uri: fully qualified libvirt uri of local system, from remote.
        :return: True/False if checks pass or not
        """
        if remote_ip is None or uri is None:
            return False
        all_false = [
            # remote_ip checks
            bool(remote_ip.count("EXAMPLE.COM")),
            bool(remote_ip.count("localhost")),
            bool(remote_ip.count("127.")),
            # uri checks
            uri is None,
            uri == "",
            bool(uri.count("default")),
            bool(uri.count(':///')),
            bool(uri.count("localhost")),
            bool(uri.count("127."))
        ]
        return True not in all_false


class EventNotFoundError(Exception):
    """
    Error when certain event cannot be found.
    """

    def __init__(self, details=''):
        self.details = details

    def __str__(self):
        return str(self.details)


class EventTracker(object):

    @staticmethod
    def start_get_event(vm_name):
        """
        Use a virsh session with subcommand 'event' to catch events

        :param vm_name: name of the vm to be catched
        :return: the virsh session with 'event'
        """
        virsh_session = aexpect.ShellSession(VIRSH_EXEC)
        event_cmd = 'event %s --all --loop' % vm_name
        LOG.info('Sending "%s" to virsh shell', event_cmd)
        virsh_session.sendline(event_cmd)

        return virsh_session

    @staticmethod
    def finish_get_event(virsh_session):
        """
        Stop virsh session and return the event output

        Usage:
        virsh_session = start_get_event(vm_name)
        ####
        virsh commands or other operations
        ####
        event_output = finish_get_event(virsh_session)

        :param virsh_session: virsh session to catch events
        :return: actual event output catched
        """
        virsh_session.send_ctrl("^C")
        time.sleep(5)
        event_output = virsh_session.get_stripped_output()
        virsh_session.close()
        LOG.debug('Event output is %s:', event_output)

        return event_output

    @staticmethod
    def wait_event(func):
        """
        Decorator aiming to return until certain type of virsh event defined
        by func was found

        Usage:
        @EventTracker.wait_event
        def func(xx, xx, ... wait_for_event=False,
                 event_type='tray-change', event_timeout=7)

        """
        @wraps(func)
        def wrapper(*args, **kwargs):

            def _get_arg_value(arg):
                return kwargs.get(arg) if arg in kwargs else \
                    inspect.signature(func).parameters[arg].default if \
                    arg in inspect.signature(func).parameters else None

            def _get_event_output(session):
                # Use get_output instead of get_stripped_output to avoid
                # missing output.
                output = session.get_output()
                LOG.debug(output)
                return output

            wait_for_event = _get_arg_value('wait_for_event')
            event_type = _get_arg_value('event_type')
            event_timeout = _get_arg_value('event_timeout')

            if wait_for_event is True and event_type is not None:
                virsh_session = EventTracker.start_get_event(str(args[0]))
                # Sometimes the output of virsh_session is missing, add a sleep
                # for debug. Will remove it if it is unnecessary.
                time.sleep(3)
                ret = func(*args, **kwargs)

                if ret and ret.exit_status:
                    LOG.error('Command execution failed. Skip waiting for event')
                    virsh_session.close()
                    return ret

                if not utils_misc.wait_for(
                        lambda: re.search(
                            event_type,
                            _get_event_output(virsh_session)
                        ), event_timeout):
                    raise EventNotFoundError('Not found event %s after %s seconds' %
                                             (event_type, event_timeout))
                virsh_session.close()
                return ret
            else:
                return func(*args, **kwargs)

        return wrapper


# virsh module functions follow (See module docstring for API) #####


def command(cmd, **dargs):
    """
    Interface to cmd function as 'cmd' symbol is polluted.

    :param cmd: Command line to append to virsh command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    :raise: CmdError if non-zero exit status and ignore_status=False
    """

    virsh_exec = dargs.get('virsh_exec', VIRSH_EXEC)
    uri = dargs.get('uri', None)
    virsh_opt = dargs.get('virsh_opt', '')
    debug = dargs.get('debug', False)
    # Caller deals with errors
    ignore_status = dargs.get('ignore_status', True)
    session_id = dargs.get('session_id', None)
    readonly = dargs.get('readonly', False)
    quiet = dargs.get('quiet', False)
    unprivileged_user = dargs.get('unprivileged_user', None)
    timeout = dargs.get('timeout', None)

    # Check if this is a VirshPersistent method call
    if session_id:
        # Retrieve existing session
        session = VirshSession(a_id=session_id)
    else:
        session = None

    if debug:
        LOG.debug("Running virsh command: %s", cmd)

    if timeout:
        try:
            timeout = int(timeout)
        except ValueError:
            LOG.error("Ignore the invalid timeout value: %s", timeout)
            timeout = None

    if session:
        # Utilize persistent virsh session, not suit for readonly mode
        if readonly:
            LOG.debug("Ignore readonly flag for this virsh session")
        if timeout is None:
            timeout = 60
        ret = session.cmd_result(cmd, ignore_status=ignore_status,
                                 debug=debug, timeout=timeout)
        # Mark return value with session it came from
        ret.from_session_id = session_id
    else:
        # Normal call to run virsh command
        # Readonly mode
        if readonly:
            cmd = " -r " + cmd

        if quiet:
            cmd = " -q " + cmd

        if uri:
            # uri argument IS being used
            uri_arg = " -c '%s' " % uri
        else:
            uri_arg = " "  # No uri argument being used

        cmd = "%s%s%s%s" % (virsh_exec, virsh_opt, uri_arg, cmd)
        if unprivileged_user:
            # Run cmd as unprivileged user
            cmd = "su - %s -c '%s'" % (unprivileged_user, cmd)

        # Raise exception if ignore_status is False
        ret = process.run(cmd, timeout=timeout, verbose=debug,
                          ignore_status=ignore_status,
                          shell=True)
        # Mark return as not coming from persistent virsh session
        ret.from_session_id = None
        ret.stdout = ret.stdout_text
        ret.stderr = ret.stderr_text

    # Always log debug info, if persistent session or not
    if debug:
        LOG.debug("status: %s", ret.exit_status)
        LOG.debug("stdout: %s", ret.stdout_text.strip())
        LOG.debug("stderr: %s", ret.stderr_text.strip())

    # Return CmdResult instance when ignore_status is True
    return ret


def domname(dom_id_or_uuid, **dargs):
    """
    Convert a domain id or UUID to domain name

    :param dom_id_or_uuid: a domain id or UUID.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("domname --domain %s" % dom_id_or_uuid, **dargs)


def qemu_monitor_command(name, cmd, options="", **dargs):
    """
    This helps to execute the qemu monitor command through virsh command.

    :param name: Name of monitor domain
    :param cmd: monitor command to execute
    :param options: extra options
    :param dargs: standardized virsh function API keywords
    """
    cmd_str = "qemu-monitor-command %s %s --cmd \'%s\'" % (name, options, cmd)
    return command(cmd_str, **dargs)


def qemu_agent_command(name, cmd, options="", **dargs):
    """
    This helps to execute the qemu agent command through virsh command.

    :param name: Name of monitor domain
    :param cmd: agent command to execute
    :param options: extra options
    :param dargs: standardized virsh function API keywords
    """
    cmd_str = "qemu-agent-command %s %s --cmd \'%s\'" % (name, options, cmd)
    return command(cmd_str, **dargs)


def qemu_attach(pid, extra="", **dargs):
    """
    This helps to execute the qemu-attach command through virsh command.

    :param pid: pid of qemu process
    :param extra: extra options
    :param dargs: standardized virsh function API keywords
    """
    cmd_str = "qemu-attach --pid %s %s" % (pid, extra)
    return command(cmd_str, **dargs)


def setvcpus(name, count, extra="", **dargs):
    """
    Change the number of virtual CPUs in the guest domain.

    :param name: name of vm to affect
    :param count: value for vcpu parameter
    :param options: any extra command options.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object from command
    """
    cmd = "setvcpus %s %s %s" % (name, count, extra)
    return command(cmd, **dargs)


def setvcpu(name, cpulist, extra="", **dargs):
    """
    attach/detach vcpu or groups of threads

    :param name: name of vm to affect
    :param cpulist: group of vcpu numbers
    :param options: any extra command options.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object from command
    """
    cmd = "setvcpu %s %s %s" % (name, cpulist, extra)
    return command(cmd, **dargs)


def guestvcpus(name, cpu_list=None, options=None, **dargs):
    """
    Query or modify state of vcpu in the guest (via agent)
    :param name: name of domain
    :param cpu_list: list of cpus to enable or disable
    :param options: --enable, --disable
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "guestvcpus --domain %s" % name
    if cpu_list:
        cmd += " --cpulist %s" % cpu_list
    if options:
        cmd += " %s" % options
    return command(cmd, **dargs)


def vcpupin(name, vcpu=None, cpu_list=None, options=None, **dargs):
    """
    Changes the cpu affinity for respective vcpu.

    :param name: name of domain
    :param vcpu: virtual CPU to modify
    :param cpu_list: physical CPU specification (string)
    :param dargs: standardized virsh function API keywords
    :param options: --live, --current or --config.
    :return: CmdResult object.
    """
    cmd = "vcpupin --domain %s" % name
    if vcpu is not None:
        cmd += " --vcpu %s" % vcpu
    if cpu_list is not None:
        cmd += " --cpulist %s" % cpu_list
    if options is not None:
        cmd += " %s" % options
    return command(cmd, **dargs)


def vcpuinfo(name, options=None, **dargs):
    """
    :param name: name of domain
    :param options: --pretty so far
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "vcpuinfo %s" % name
    if options is not None:
        cmd += " %s" % options
    return command(cmd, **dargs)


def freecell(cellno=None, options="", **dargs):
    """
    Prints the available amount of memory on the machine or within a NUMA cell.

    :param cellno: number of cell to show.
    :param options: extra argument string to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "freecell "
    if cellno:
        cmd = "%s --cellno %s " % (cmd, cellno)
    cmd = "%s %s" % (cmd, options)
    return command(cmd, **dargs)


def nodeinfo(extra="", **dargs):
    """
    Returns basic information about the node,like number and type of CPU,
    and size of the physical memory.

    :param extra: extra argument string to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd_nodeinfo = "nodeinfo %s" % extra
    return command(cmd_nodeinfo, **dargs)


def nodecpumap(extra="", **dargs):
    """
    Displays the node's total number of CPUs, the number of online
    CPUs and the list of online CPUs.

    :param extra: extra argument string to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nodecpumap %s" % extra
    return command(cmd, **dargs)


def nodesuspend(target, duration, extra='', **dargs):
    """
    Suspend the host node for a given time duration.

    :param target: Suspend target mem/disk/hybrid.
                   mem(Suspend-to-RAM)
                   disk(Suspend-to-Disk)
                   hybrid(Hybrid-Suspend)
    :param duration: Suspend duration in seconds, at least 60.
    :param extra: extra argument string to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nodesuspend %s %s" % (target, duration)
    if extra:
        cmd += " %s" % extra
    return command(cmd, **dargs)


def canonical_uri(option='', **dargs):
    """
    Return the hypervisor canonical URI.

    :param option: additional option string to pass
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    result = command("uri %s" % option, **dargs)
    return result.stdout_text.strip()


def hostname(option='', **dargs):
    """
    Return the hypervisor hostname.

    :param option: additional option string to pass
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    result = command("hostname %s" % option, **dargs)
    return result.stdout_text.strip()


def version(option='', **dargs):
    """
    Return the major version info about what this built from.

    :param option: additional option string to pass
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("version %s" % option, **dargs)


def maxvcpus(option='', **dargs):
    """
    Return the connection vcpu maximum number.

    :param: option: additional option string to pass
    :param: dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "maxvcpus %s" % option
    return command(cmd, **dargs)


def dom_list(options="", **dargs):
    """
    Return the list of domains.

    :param options: options to pass to list command
    :return: CmdResult object
    """
    return command("list %s" % options, **dargs)


def reboot(name, options="", **dargs):
    """
    Run a reboot command in the target domain.

    :param name: Name of domain.
    :param options: options to pass to reboot command
    :return: CmdResult object
    """
    return command("reboot --domain %s %s" % (name, options), **dargs)


def managedsave(name, options="", **dargs):
    """
    Managed save of a domain state.

    :param name: Name of domain to save
    :param options: options to pass to list command
    :return: CmdResult object
    """
    return command("managedsave --domain %s %s" % (name, options), **dargs)


def managedsave_remove(name, **dargs):
    """
    Remove managed save of a domain

    :param name: name of managed-saved domain to remove
    :return: CmdResult object
    """
    return command("managedsave-remove --domain %s" % name, **dargs)


def managedsave_dumpxml(name, options="", **dargs):
    """
    Dump XML of domain information for a managed save state file.

    :param name: Name of domain to dump
    :param options: options to pass to list command
    :return: CmdResult object
    """
    return command("managedsave-dumpxml --domain %s %s" % (name, options), **dargs)


def managedsave_edit(name, options="", **dargs):
    """
    Edit the domain XML associated with the managed save state file.

    :param name: Name of domain to edit
    :param options: options to pass to list command
    :return: CmdResult object
    """
    return command("managedsave-edit --domain %s %s" % (name, options), **dargs)


def managedsave_define(name, xml_path, options="", **dargs):
    """
    Replace the domain XML associated with a managed save state file.

    :param name: Name of domain to define
    :param xml_path: Path of xml file to be defined
    :param options: options to pass to list command
    :return: CmdResult object
    """
    return command("managedsave-define --domain %s %s %s" % (name, xml_path, options), **dargs)


def driver(**dargs):
    """
    Return the driver by asking libvirt

    :param dargs: standardized virsh function API keywords
    :return: VM driver name
    """
    # libvirt schme composed of driver + command
    # ref: http://libvirt.org/uri.html
    scheme = urllib.parse.urlsplit(canonical_uri(**dargs))[0]
    # extract just the driver, whether or not there is a '+'
    return scheme.split('+', 2)[0]


def domstate(name, extra="", **dargs):
    """
    Return the state about a running domain.

    :param name: VM name
    :param extra: command options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("domstate %s %s" % (name, extra), **dargs)


def domid(name_or_uuid, **dargs):
    """
    Return VM's ID.

    :param name_or_uuid: VM name or uuid
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("domid %s" % (name_or_uuid), **dargs)


def dominfo(name, **dargs):
    """
    Return the VM information.

    :param name: VM's name or id,uuid.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("dominfo %s" % (name), **dargs)


def domfsinfo(name, **dargs):
    """
    Return the info of domain mounted fssystems

    :param name: VM's name or uuid.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("domfsinfo %s" % (name), **dargs)


def domuuid(name_or_id, **dargs):
    """
    Return the Converted domain name or id to the domain UUID.

    :param name_or_id: VM name or id
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("domuuid %s" % name_or_id, **dargs)


def screenshot(name, filename, **dargs):
    """
    Capture a screenshot of VM's console and store it in file on host

    :param name: VM name
    :param filename: name of host file
    :param dargs: standardized virsh function API keywords
    :return: filename
    """
    # Don't take screenshots of shut-off domains
    if is_dead(name, **dargs):
        return None
    global SCREENSHOT_ERROR_COUNT
    dargs['ignore_status'] = False
    try:
        command("screenshot %s %s" % (name, filename), **dargs)
    except process.CmdError as detail:
        if SCREENSHOT_ERROR_COUNT < 1:
            LOG.error("Error taking VM %s screenshot. You might have to "
                      "set take_regular_screendumps=no on your "
                      "tests.cfg config file \n%s.  This will be the "
                      "only logged error message.", name, detail)
        SCREENSHOT_ERROR_COUNT += 1
    return filename


def screenshot_test(name, filename="", options="", **dargs):
    """
    Capture a screenshot of VM's console and store it in file on host

    :param name: VM name or id
    :param filename: name of host file
    :param options: command options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("screenshot %s %s %s" % (name, filename, options), **dargs)


def domblkstat(name, device, option, **dargs):
    """
    Store state of VM into named file.

    :param name: VM's name.
    :param device: VM's device.
    :param option: command domblkstat option.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("domblkstat %s %s %s" % (name, device, option), **dargs)


def domblkthreshold(name, device, threshold, option="", **dargs):
    """
    Set the threshold for block-threshold event for a given block device or it's backing chain element.

    :param name: VM's name.
    :param device: VM's device.
    :param threshold: threshold value with unit such as 100M.
    :param option: command domblkthreshold option.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("domblkthreshold %s %s %s %s" % (name, device, threshold, option), **dargs)


def dumpxml(name, extra="", to_file="", **dargs):
    """
    Return the domain information as an XML dump.

    :param name: VM name
    :param to_file: optional file to write XML output to
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """
    cmd = "dumpxml %s %s" % (name, extra)
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout_text.strip())
        result_file.close()
    return result


def domifstat(name, interface, **dargs):
    """
    Get network interface stats for a running domain.

    :param name: Name of domain
    :param interface: interface device
    :return: CmdResult object
    """
    return command("domifstat %s %s" % (name, interface), **dargs)


def domjobinfo(name, extra="", **dargs):
    """
    Get domain job information.

    :param name: VM name
    :param extra: extra options to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("domjobinfo %s %s" % (name, extra), **dargs)


def edit(options, **dargs):
    """
    Edit the XML configuration for a domain.

    :param options: virsh edit options string.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("edit %s" % options, **dargs)


def dompmsuspend(name, target, duration=0, **dargs):
    """
    Suspends a running domain using guest OS's power management.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "dompmsuspend %s %s --duration %s" % (name, target, duration)
    return command(cmd, **dargs)


def dompmwakeup(name, **dargs):
    """
     Wakeup a domain that was previously suspended by power management.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("dompmwakeup %s" % name, **dargs)


def domjobabort(name, **dargs):
    """
    Aborts the currently running domain job.

    :param name: VM's name, id or uuid.
    :param dargs: standardized virsh function API keywords
    :return: result from command
    """
    return command("domjobabort %s" % name, **dargs)


def domxml_from_native(info_format, native_file, options=None, **dargs):
    """
    Convert native guest configuration format to domain XML format.

    :param info_format:The command's options. For example:qemu-argv.
    :param native_file:Native information file.
    :param options:extra param.
    :param dargs: standardized virsh function API keywords.
    :return: result from command
    """
    cmd = "domxml-from-native %s %s %s" % (info_format, native_file, options)
    return command(cmd, **dargs)


def domxml_to_native(info_format, name, options, **dargs):
    """
    Convert existing domain or its XML config to a native guest configuration format.

    :param info_format:The command's options. For example: `qemu-argv`.
    :param name: XML file or domain name/UUID.
    :param options: --xml or --domain
    :param dargs: standardized virsh function API keywords
    :return: result from command
    """
    cmd = "domxml-to-native %s %s %s" % (info_format, options, name)
    return command(cmd, **dargs)


def vncdisplay(name, **dargs):
    """
    Output the IP address and port number for the VNC display.

    :param name: VM's name or id,uuid.
    :param dargs: standardized virsh function API keywords.
    :return: result from command
    """
    return command("vncdisplay %s" % name, **dargs)


def is_alive(name, **dargs):
    """
    Return True if the domain is started/alive.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: True operation was successful
    """
    return not is_dead(name, **dargs)


def is_dead(name, **dargs):
    """
    Return True if the domain is undefined or not started/dead.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: True operation was successful
    """
    dargs['ignore_status'] = False
    try:
        state = domstate(name, **dargs).stdout_text.strip()
    except process.CmdError:
        return True
    if state not in ('running', 'idle', 'paused', 'in shutdown', 'shut off',
                     'crashed', 'pmsuspended', 'no state'):
        LOG.debug("State '%s' not known", state)
    if state in ('shut off', 'crashed', 'no state'):
        return True
    return False


def suspend(name, **dargs):
    """
    True on successful suspend of VM - kept in memory and not scheduled.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("suspend %s" % (name), **dargs)


def resume(name, **dargs):
    """
    True on successful moving domain out of suspend

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("resume %s" % (name), **dargs)


def dommemstat(name, extra="", **dargs):
    """
    Store state of VM into named file.

    :param name: VM name
    :param extra: extra options to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("dommemstat %s %s" % (name, extra), **dargs)


def dump(name, path, option="", **dargs):
    """
    Dump the core of a domain to a file for analysis.

    :param name: VM name
    :param path: absolute path to state file
    :param option: command's option.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("dump %s %s %s" % (name, path, option), **dargs)


def save(name, path, options="", **dargs):
    """
    Store state of VM into named file.

    :param name: VM name, id or uuid.
    :param path: absolute path to state file
    :param options: command's options.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("save %s %s %s" % (name, path, options), **dargs)


def restore(path, options="", **dargs):
    """
    Load state of VM from named file and remove file.

    :param path: absolute path to state file.
    :param options: options for virsh restore.
    :param dargs: standardized virsh function API keywords
    """
    return command("restore %s %s" % (path, options), **dargs)


def start(name, options="", **dargs):
    """
    True on successful start of (previously defined) inactive domain.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """
    return command("start %s %s" % (name, options), **dargs)


def shutdown(name, options="", **dargs):
    """
    True on successful domain shutdown.

    :param name: VM name
    :param options: options for virsh shutdown.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("shutdown %s %s" % (name, options), **dargs)


def destroy(name, options="", **dargs):
    """
    True on successful domain destruction

    :param name: VM name
    :param options: options for virsh destroy
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("destroy %s %s" % (name, options), **dargs)


def define(xml_path, options=None, **dargs):
    """
    Return cmd result of domain define.

    :param xml_path: XML file path
    :param options: options for virsh define
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "define --file %s" % xml_path
    if options is not None:
        cmd += " %s" % options
    LOG.debug("Define VM from %s", xml_path)
    return command(cmd, **dargs)


def undefine(name, options=None, **dargs):
    """
    Return cmd result of domain undefine (after shutdown/destroy).

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "undefine %s" % name
    if options is not None:
        cmd += " %s" % options

    if platform.machine() == "aarch64":
        if options is None or "--nvram" not in options:
            cmd += " --nvram"

    LOG.debug("Undefine VM %s", name)
    return command(cmd, **dargs)


def remove_domain(name, options=None, **dargs):
    """
    Return True after forcefully removing a domain if it exists.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: True operation was successful
    """
    if domain_exists(name, **dargs):
        if is_alive(name, **dargs):
            destroy(name, **dargs)
        try:
            dargs['ignore_status'] = False
            undefine(name, options, **dargs)
        except process.CmdError as detail:
            LOG.error("Undefine VM %s failed:\n%s", name, detail)
            return False
    return True


def domain_exists(name, **dargs):
    """
    Return True if a domain exits.

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: True operation was successful
    """
    dargs['ignore_status'] = False
    try:
        command("domstate %s" % name, **dargs)
        return True
    except process.CmdError as detail:
        LOG.warning("VM %s does not exist", name)
        if dargs.get('debug', False):
            LOG.warning(str(detail))
        return False


def migrate_postcopy(name, **dargs):
    """
    Trigger postcopy migration

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "migrate-postcopy %s" % name
    return command(cmd, **dargs)


def migrate(name="", dest_uri="", option="", extra="", **dargs):
    """
    Migrate a guest to another host.

    :param name: name of guest on uri.
    :param dest_uri: libvirt uri to send guest to
    :param option: Free-form string of options to virsh migrate
    :param extra: Free-form string of options to follow <domain> <desturi>
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "migrate"
    if option:
        cmd += " %s" % option
    if name:
        cmd += " --domain %s" % name
    if dest_uri:
        cmd += " --desturi %s" % dest_uri
    if extra:
        cmd += " %s" % extra

    return command(cmd, **dargs)


def migrate_setspeed(domain, bandwidth, extra=None, **dargs):
    """
    Set the maximum migration bandwidth (in MiB/s) for
    a domain which is being migrated to another host.

    :param domain: name/uuid/id of guest
    :param bandwidth: migration bandwidth limit in MiB/s
    :param dargs: standardized virsh function API keywords
    """

    cmd = "migrate-setspeed %s %s" % (domain, bandwidth)
    if extra is not None:
        cmd += " %s" % extra
    return command(cmd, **dargs)


def migrate_getspeed(domain, extra="", **dargs):
    """
    Get the maximum migration bandwidth (in MiB/s) for
    a domain.

    :param domain: name/uuid/id of guest
    :param extra: extra options to migrate-getspeed
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    cmd = "migrate-getspeed %s" % domain
    if extra:
        cmd += " %s" % extra
    return command(cmd, **dargs)


def migrate_setmaxdowntime(domain, downtime, extra=None, **dargs):
    """
    Set maximum tolerable downtime of a domain (in ms)
    which is being live-migrated to another host.

    :param domain: name/uuid/id of guest
    :param downtime: downtime number of live migration
    """
    cmd = "migrate-setmaxdowntime %s %s" % (domain, downtime)
    if extra is not None:
        cmd += " %s" % extra
    return command(cmd, **dargs)


def migrate_getmaxdowntime(domain, **dargs):
    """
    Get maximum tolerable downtime of a domain.

    :param domain: name/uuid/id of guest
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    cmd = "migrate-getmaxdowntime %s" % domain
    return command(cmd, **dargs)


def migrate_compcache(domain, size=None, **dargs):
    """
    Get/set compression cache size for migration.

    :param domain: name/uuid/id of guest
    :param size: compression cache size to be set.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = 'migrate-compcache %s' % domain
    if size is not None:
        cmd += ' --size %s' % size
    return command(cmd, **dargs)


def _adu_device(action, domainarg=None, filearg=None,
                domain_opt=None, file_opt=None,
                flagstr=None, **dargs):
    """
    Private helper for attach, detach, update device commands
    """
    # N/B: Parameter order is significant: RH BZ 1018369
    cmd = action
    if domain_opt is not None:
        cmd += " --domain %s" % domain_opt
    if domainarg is not None:
        cmd += " %s" % domainarg
    if file_opt is not None:
        cmd += " --file %s" % file_opt
    if filearg is not None:
        cmd += " %s" % filearg
    if flagstr is not None:
        cmd += " %s" % flagstr
    return command(cmd, **dargs)


def attach_device(domainarg=None, filearg=None,
                  domain_opt=None, file_opt=None,
                  flagstr=None, **dargs):
    """
    Attach a device using full parameter/argument set.

    :param domainarg: Domain name (first pos. parameter)
    :param filearg: File name (second pos. parameter)
    :param domain_opt: Option to --domain parameter
    :param file_opt: Option to --file parameter
    :param flagstr: string of "--force, --persistent, etc."
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return _adu_device("attach-device", domainarg=domainarg, filearg=filearg,
                       domain_opt=domain_opt, file_opt=file_opt,
                       flagstr=flagstr, **dargs)


@EventTracker.wait_event
def detach_device(domainarg=None, filearg=None,
                  domain_opt=None, file_opt=None,
                  flagstr=None, wait_for_event=False,
                  event_type='device-removed', event_timeout=7, **dargs):
    """
    Detach a device using full parameter/argument set.

    :param domainarg: Domain name (first pos. parameter)
    :param filearg: File name (second pos. parameter)
    :param domain_opt: Option to --domain parameter
    :param file_opt: Option to --file parameter
    :param flagstr: string of "--force, --persistent, etc."
    :param wait_for_event: wait until device_remove event comes
    :param event_type: type of the event
    :param event_timeout: timeout for virsh event command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    detach_cmd_rv = _adu_device("detach-device", domainarg=domainarg, filearg=filearg,
                                domain_opt=domain_opt, file_opt=file_opt,
                                flagstr=flagstr, **dargs)
    return detach_cmd_rv


def update_device(domainarg=None, filearg=None,
                  domain_opt=None, file_opt=None,
                  flagstr="", **dargs):
    """
    Update device from an XML <file>.

    :param domainarg: Domain name (first pos. parameter)
    :param filearg: File name (second pos. parameter)
    :param domain_opt: Option to --domain parameter
    :param file_opt: Option to --file parameter
    :param flagstr: string of "--force, --persistent, etc."
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return _adu_device("update-device", domainarg=domainarg, filearg=filearg,
                       domain_opt=domain_opt, file_opt=file_opt,
                       flagstr=flagstr, **dargs)


def attach_disk(name, source, target, extra="", **dargs):
    """
    Attach a disk to VM.

    :param name: name of guest
    :param source: source of disk device
    :param target: target of disk device
    :param extra: additional arguments to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "attach-disk --domain %s --source %s --target %s %s"\
        % (name, source, target, extra)
    return command(cmd, **dargs)


def detach_disk(name, target, extra="", wait_remove_event=False, event_timeout=7, **dargs):
    """
    Detach a disk from VM.

    :param name: name of guest
    :param target: target of disk device
    :param wait_remove_event: wait until device_remove event comes
    :param event_timeout: timeout for virsh event command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    detach_cmd = "detach-disk --domain %s --target %s %s" % (name, target, extra)
    detach_cmd_rv = command(detach_cmd, **dargs)
    if wait_remove_event:
        event(domain=name, event='device-removed', event_timeout=event_timeout, **dargs)

    return detach_cmd_rv


@EventTracker.wait_event
def detach_device_alias(name, alias, extra="", wait_for_event=False,
                        event_type='device-removed', event_timeout=7, **dargs):
    """
    Detach a device with alias

    :param name: name of guest
    :param alias: alias of device
    :param extra: additional arguments to command
    :param wait_for_event: wait until device_remove event comes
    :param event_type: type of the event
    :param event_timeout: timeout for virsh event command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    detach_cmd = "detach-device-alias --domain %s --alias %s %s" % (name, alias, extra)
    detach_cmd_rv = command(detach_cmd, **dargs)
    return detach_cmd_rv


def attach_interface(name, option="", **dargs):
    """
    Attach a NIC to VM.

    :param name: name of guest
    :param option: options to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "attach-interface "

    if name:
        cmd += "--domain %s" % name
    if option:
        cmd += " %s" % option

    return command(cmd, **dargs)


def detach_interface(name, option="", wait_remove_event=False, event_timeout=7, **dargs):
    """
    Detach a NIC to VM.

    :param name: name of guest
    :param option: options to pass to command
    :param wait_remove_event: wait until device_remove event comes
    :param event_timeout: timeout for virsh event command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    detach_cmd = "detach-interface --domain %s %s" % (name, option)
    detach_cmd_rv = command(detach_cmd, **dargs)
    if wait_remove_event:
        event(domain=name, event='device-removed', event_timeout=event_timeout, **dargs)

    return detach_cmd_rv


def net_dumpxml(name, extra="", to_file="", **dargs):
    """
    Dump XML from network named param name.

    :param name: Name of a network
    :param extra: Extra parameters to pass to command
    :param to_file: Send result to a file
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "net-dumpxml %s %s" % (name, extra)
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    return result


def net_create(xml_file, extra="", **dargs):
    """
    Create _transient_ network from a XML file.

    :param xml_file: xml defining network
    :param extra: extra parameters to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-create %s %s" % (xml_file, extra), **dargs)


def net_define(xml_file, extra="", **dargs):
    """
    Define network from a XML file, do not start

    :param xml_file: xml defining network
    :param extra: extra parameters to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-define %s %s" % (xml_file, extra), **dargs)


def net_list(options, extra="", **dargs):
    """
    List networks on host.

    :param options: options to pass to command
    :param extra: extra parameters to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-list %s %s" % (options, extra), **dargs)


def net_state_dict(only_names=False, virsh_instance=None, **dargs):
    """
    Return network name to state/autostart/persistent mapping

    :param only_names: When true, return network names as keys and None values
    :param virsh_instance: Call net_list() on this instance instead of module
    :param dargs: standardized virsh function API keywords
    :return: dictionary
    """
    # Using multiple virsh commands in different ways
    dargs['ignore_status'] = False  # force problem detection
    if virsh_instance is not None:
        net_list_result = virsh_instance.net_list("--all", **dargs)
    else:
        net_list_result = net_list("--all", **dargs)
    # If command failed, exception would be raised here
    netlist = net_list_result.stdout_text.strip().splitlines()
    # First two lines contain table header followed by entries
    # for each network on the host, such as:
    #
    #   Name                 State      Autostart     Persistent
    #  ----------------------------------------------------------
    #   default              active     yes           yes
    #
    # TODO: Double-check first-two lines really are header
    netlist = netlist[2:]
    result = {}
    for line in netlist:
        # Split on whitespace, assume 3 columns
        linesplit = line.split(None, 3)
        name = linesplit[0]
        # Several callers in libvirt_xml only require defined names
        if only_names:
            result[name] = None
            continue
        # Keep search fast & avoid first-letter capital problems
        active = not bool(linesplit[1].count("nactive"))
        autostart = bool(linesplit[2].count("es"))
        if len(linesplit) == 4:
            persistent = bool(linesplit[3].count("es"))
        else:
            # There is no representation of persistent status in output
            # in older libvirt. When libvirt older than 0.10.2 no longer
            # supported, this block can be safely removed.
            try:
                # Rely on net_autostart will raise() if not persistent state
                if autostart:  # Enabled, try enabling again
                    # dargs['ignore_status'] already False
                    if virsh_instance is not None:
                        virsh_instance.net_autostart(name, **dargs)
                    else:
                        net_autostart(name, **dargs)
                else:  # Disabled, try disabling again
                    if virsh_instance is not None:
                        virsh_instance.net_autostart(
                            name, "--disable", **dargs)
                    else:
                        net_autostart(name, "--disable", **dargs)
                # no exception raised, must be persistent
                persistent = True
            except process.CmdError as detail:
                # Exception thrown, could be transient or real problem
                if bool(str(detail.result).count("ransient")):
                    persistent = False
                else:  # A unexpected problem happened, re-raise it.
                    raise
        # Warning: These key names are used by libvirt_xml and test modules!
        result[name] = {'active': active,
                        'autostart': autostart,
                        'persistent': persistent}
    return result


def net_start(network, extra="", **dargs):
    """
    Start network on host.

    :param network: name/parameter for network option/argument
    :param extra: extra parameters to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-start %s %s" % (network, extra), **dargs)


def net_destroy(network, extra="", **dargs):
    """
    Destroy (stop) an activated network on host.

    :param network: name/parameter for network option/argument
    :param extra: extra string to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-destroy %s %s" % (network, extra), **dargs)


def net_undefine(network, extra="", **dargs):
    """
    Undefine a defined network on host.

    :param network: name/parameter for network option/argument
    :param extra: extra string to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-undefine %s %s" % (network, extra), **dargs)


def net_name(uuid, extra="", **dargs):
    """
    Get network name on host.

    :param uuid: network UUID.
    :param extra: extra parameters to pass to command.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-name %s %s" % (uuid, extra), **dargs)


def net_uuid(network, extra="", **dargs):
    """
    Get network UUID on host.

    :param network: name/parameter for network option/argument
    :param extra: extra parameters to pass to command.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-uuid %s %s" % (network, extra), **dargs)


def net_autostart(network, extra="", **dargs):
    """
    Set/unset a network to autostart on host boot

    :param network: name/parameter for network option/argument
    :param extra: extra parameters to pass to command (e.g. --disable)
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("net-autostart %s %s" % (network, extra), **dargs)


def net_info(network, extra="", **dargs):
    """
    Get network information

    :param network: name/parameter for network option/argument
    :param extra: extra parameters to pass to command.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("net-info %s %s" % (network, extra), **dargs)


def net_update(network, update_cmd, section, xml, extra="", **dargs):
    """
    Update parts of an existing network's configuration

    :param network: network name or uuid
    :param update_cmd: type of update (add-first, add-last, delete, or modify)
    :param section: which section of network configuration to update
    :param xml: name of file containing xml
    :param extra: extra parameters to pass to command.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "net-update %s %s %s %s %s" \
          % (network, update_cmd, section, xml, extra)
    return command(cmd, **dargs)


def _pool_type_check(pool_type):
    """
    check if the pool_type is supported or not

    :param pool_type: pool type
    :return: valid pool type or None
    """
    valid_types = ['dir', 'fs', 'netfs', 'disk', 'iscsi', 'logical',
                   'gluster', 'rbd', 'scsi', 'iscsi-direct']

    if pool_type and pool_type not in valid_types:
        LOG.error("Specified pool type '%s' not in '%s'",
                  pool_type, valid_types)
        pool_type = None
    elif not pool_type:
        # take the first element as default pool_type
        pool_type = valid_types[0]
    return pool_type


def pool_info(name, **dargs):
    """
    Returns basic information about the storage pool.

    :param name: name of pool
    :param dargs: standardized virsh function API keywords
    """
    cmd = "pool-info %s" % name
    return command(cmd, **dargs)


def pool_destroy(name, **dargs):
    """
    Forcefully stop a given pool.

    :param name: name of pool
    :param dargs: standardized virsh function API keywords
    """
    cmd = "pool-destroy %s" % name
    dargs['ignore_status'] = False
    try:
        command(cmd, **dargs)
        return True
    except process.CmdError as detail:
        LOG.error("Failed to destroy pool: %s.", detail)
        return False


def pool_create(xml_file, extra="", **dargs):
    """
    Create a pool from an xml file.

    :param xml_file: file containing an XML pool description
    :param extra: extra parameters to pass to command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("pool-create %s %s" % (extra, xml_file), **dargs)


def pool_create_as(name, pool_type, target, extra="", **dargs):
    """
    Create a pool from a set of args.

    :param name: name of pool
    :param pool_type: storage pool type such as 'dir'
    :param target: libvirt uri to send guest to
    :param extra: Free-form string of options
    :param dargs: standardized virsh function API keywords
    :return: True if pool creation command was successful
    """

    if not name:
        LOG.error("Please give a pool name")

    pool_type = _pool_type_check(pool_type)
    if pool_type is None:
        return False

    LOG.info("Create %s type pool %s", pool_type, name)
    cmd = "pool-create-as --name %s --type %s --target %s %s" \
          % (name, pool_type, target, extra)
    dargs['ignore_status'] = False
    try:
        command(cmd, **dargs)
        return True
    except process.CmdError as detail:
        LOG.error("Failed to create pool: %s.", detail)
        return False


def pool_list(option="", extra="", **dargs):
    """
    Prints the pool information of Host.

    :param option: options given to command

    all
        gives all pool details, including inactive
    inactive
        gives only inactive pool details
    details
        Gives the complete details about the pools

    :param extra: to provide extra options(to enter invalid options)
    """
    return command("pool-list %s %s" % (option, extra), **dargs)


def pool_uuid(name, **dargs):
    """
    Convert a pool name to pool UUID

    :param name: Name of the pool
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("pool-uuid %s" % name, **dargs)


def pool_name(uuid, **dargs):
    """
    Convert a pool UUID to pool name

    :param name: UUID of the pool
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("pool-name %s" % uuid, **dargs)


def pool_refresh(name, **dargs):
    """
    Refresh a pool

    :param name: Name of the pool
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("pool-refresh %s" % name, **dargs)


def pool_delete(name, **dargs):
    """
    Delete the resources used by a given pool object

    :param name: Name of the pool
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("pool-delete %s" % name, **dargs)


def pool_state_dict(only_names=False, **dargs):
    """
    Return pool name to state/autostart mapping

    :param only_names: When true, return pool names as keys and None values
    :param dargs: standardized virsh function API keywords
    :return: dictionary
    """
    # Using multiple virsh commands in different ways
    dargs['ignore_status'] = False  # force problem detection
    pool_list_result = pool_list("--all", **dargs)
    # If command failed, exception would be raised here
    poollist = pool_list_result.stdout_text.strip().splitlines()
    # First two lines contain table header followed by entries
    # for each pool on the host, such as:
    #
    #   Name                 State      Autostart
    #  -------------------------------------------
    #   default              active     yes
    #   iscsi-net-pool       active     yes
    #
    # TODO: Double-check first-two lines really are header
    poollist = poollist[2:]
    result = {}
    for line in poollist:
        # Split on whitespace, assume 3 columns
        linesplit = line.split(None, 3)
        name = linesplit[0]
        # Several callers in libvirt_xml only require defined names
        #  TODO: Copied from net_state_dict where this is true, but
        #        as of writing only caller is virsh_pool_create test
        #        which doesn't use this 'feature'.
        if only_names:
            result[name] = None
            continue
        # Keep search fast & avoid first-letter capital problems
        active = not bool(linesplit[1].count("nactive"))
        autostart = bool(linesplit[2].count("es"))

        # Warning: These key names are used by libvirt_xml and test modules!
        result[name] = {'active': active,
                        'autostart': autostart}
    return result


def pool_define_as(name, pool_type, target="", extra="", **dargs):
    """
    Define the pool from the arguments

    :param name: Name of the pool to be defined
    :param pool_type: Type of the pool to be defined

        dir
            file system directory
        disk
            Physical Disk Device
        fs
            Pre-formatted Block Device
        netfs
            Network Exported Directory
        iscsi
            iSCSI Target
        logical
            LVM Volume Group
        mpath
            Multipath Device Enumerater
        scsi
            SCSI Host Adapter
        rbd
            Rados Block Device

    :param target: libvirt uri to send guest to
    :param extra: Free-form string of options
    :param dargs: standardized virsh function API keywords
    :return: True if pool define command was successful
    """

    pool_type = _pool_type_check(pool_type)
    if pool_type is None:
        return False

    LOG.debug("Try to define %s type pool %s", pool_type, name)
    cmd = "pool-define-as --name %s --type %s %s" \
          % (name, pool_type, extra)
    # Target is not a must
    if target:
        cmd += " --target %s" % target
    return command(cmd, **dargs)


def pool_start(name, extra="", **dargs):
    """
    Start the defined pool

    :param name: Name of the pool to be started
    :param extra: Free-form string of options
    :param dargs: standardized virsh function API keywords
    :return: True if pool start command was successful
    """
    return command("pool-start %s %s" % (name, extra), **dargs)


def pool_autostart(name, extra="", **dargs):
    """
    Mark for autostart of a pool

    :param name: Name of the pool to be mark for autostart
    :param extra: Free-form string of options
    :param dargs: standardized virsh function API keywords
    :return: True if pool autostart command was successful
    """
    return command("pool-autostart %s %s" % (name, extra), **dargs)


def pool_edit(name, **dargs):
    """
    Edit XML configuration for a storage pool.

    :param name: pool name or uuid
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "pool-edit %s" % name
    return command(cmd, **dargs)


def pool_undefine(name, extra="", **dargs):
    """
    Undefine the given pool

    :param name: Name of the pool to be undefined
    :param extra: Free-form string of options
    :param dargs: standardized virsh function API keywords
    :return: True if pool undefine command was successful
    """
    return command("pool-undefine %s %s" % (name, extra), **dargs)


def pool_build(name, options="", **dargs):
    """
    Build pool.

    :param name: Name of the pool to be built
    :param options: options for pool-build
    """
    return command("pool-build %s %s" % (name, options), **dargs)


def find_storage_pool_sources_as(source_type, options="", **dargs):
    """
    Find potential storage pool sources

    :param source_type: type of storage pool sources to find
    :param options: cmd options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("find-storage-pool-sources-as %s %s"
                   % (source_type, options), **dargs)


def find_storage_pool_sources(source_type, srcSpec, **dargs):
    """
    Find potential storage pool sources

    :param source_type: type of storage pool sources to find
    :param srcSpec: file of source xml to qurey for pools
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("find-storage-pool-sources %s %s"
                   % (source_type, srcSpec), **dargs)


def pool_dumpxml(name, extra="", to_file="", **dargs):
    """
    Return the pool information as an XML dump.

    :param name: pool_name name
    :param to_file: optional file to write XML output to
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    dargs['ignore_status'] = True
    cmd = "pool-dumpxml %s %s" % (name, extra)
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    if result.exit_status:
        raise process.CmdError(cmd, result,
                               "Virsh dumpxml returned non-zero exit status")
    return result.stdout_text.strip()


def pool_define(xml_path, **dargs):
    """
    To create the pool from xml file.

    :param xml_path: XML file path
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "pool-define --file %s" % xml_path
    return command(cmd, **dargs)


def vol_create(pool_name, xml_file, extra="", **dargs):
    """
    To create the volumes from xml file.

    :param pool_name: Name of the pool to be used
    :param xml_file: file containing an XML vol description
    :param extra: string of extra options
    :return: CmdResult object
    """
    cmd = "vol-create --pool %s --file %s %s" % (pool_name, xml_file, extra)
    return command(cmd, **dargs)


def vol_create_as(volume_name, pool_name, capacity,
                  allocation, frmt, extra="", **dargs):
    """
    To create the volumes on different available pool

    :param name: Name of the volume to be created
    :param pool_name: Name of the pool to be used
    :param capacity: Size of the volume
    :param allocation: Size of the volume to be pre-allocated
    :param frmt: volume formats(e.g. raw, qed, qcow2)
    :param extra: Free-form string of options
    :param dargs: standardized virsh function API keywords
    :return: True if pool undefine command was successful
    """

    cmd = "vol-create-as --pool %s" % pool_name
    cmd += " %s --capacity %s" % (volume_name, capacity)

    if allocation:
        cmd += " --allocation %s" % (allocation)
    if frmt:
        cmd += " --format %s" % (frmt)
    if extra:
        cmd += " %s" % (extra)
    return command(cmd, **dargs)


def vol_create_from(pool_name, vol_file, input_vol, input_pool, extra="",
                    **dargs):
    """
    Create a vol, using another volume as input

    :param: pool_name: Name of the pool to create the volume in
    :param: vol_file: XML <file> with the volume definition
    :param: input_vol: Name of the source volume
    :param: input_pool: Name of the pool the source volume is in
    :param: extra: Free-form string of options
    :return: True if volume create successfully
    """
    cmd = ("vol-create-from --pool %s --file %s --vol %s --inputpool %s" %
           (pool_name, vol_file, input_vol, input_pool))
    if extra:
        cmd += " %s" % (extra)
    return command(cmd, **dargs)


def vol_list(pool_name, extra="", **dargs):
    """
    List the volumes for a given pool

    :param pool_name: Name of the pool
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("vol-list %s %s" % (pool_name, extra), **dargs)


def vol_delete(volume_name, pool_name, extra="", **dargs):
    """
    Delete a given volume

    :param volume_name: Name of the volume
    :param pool_name: Name of the pool
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("vol-delete %s %s %s" %
                   (volume_name, pool_name, extra), **dargs)


def vol_key(volume_name, pool_name, extra="", **drags):
    """
    Prints the key of the given volume name

    :param volume_name: Name of the volume
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("vol-key --vol %s --pool %s %s" %
                   (volume_name, pool_name, extra), **drags)


def vol_info(volume_name, pool_name, extra="", **drags):
    """
    Prints the given volume info

    :param volume_name: Name of the volume
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    cmd = "vol-info --vol %s" % volume_name
    if pool_name:
        cmd += " --pool %s" % pool_name
    if extra:
        cmd += " %s" % extra
    return command(cmd, **drags)


def vol_name(volume_key, extra="", **drags):
    """
    Prints the given volume name

    :param volume_name: Name of the volume
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("vol-name --vol %s %s" % (volume_key, extra), **drags)


def vol_path(volume_name, pool_name, extra="", **dargs):
    """
    Prints the give volume path

    :param volume_name: Name of the volume
    :param pool_name: Name of the pool
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("vol-path --vol %s --pool %s %s" %
                   (volume_name, pool_name, extra), **dargs)


def vol_dumpxml(volume_name, pool_name, to_file=None, options="", **dargs):
    """
    Dumps volume details in xml

    :param volume_name: Name of the volume
    :param pool_name: Name of the pool
    :param to_file: path of the file to store the output
    :param options: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    cmd = ('vol-dumpxml --vol %s --pool %s %s' %
           (volume_name, pool_name, options))
    result = command(cmd, **dargs)
    if to_file is not None:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    return result


def vol_pool(volume_name, extra="", **dargs):
    """
    Returns pool name for a given vol-key

    :param volume_name: Name of the volume
    :param extra: Free-form string options
    :param dargs: standardized virsh function API keywords
    :return: returns the output of the command
    """
    return command("vol-pool %s %s" % (volume_name, extra), **dargs)


def vol_clone(volume_name, new_name, pool_name="", extra="", **dargs):
    """
    Clone an existing volume.

    :param volume_name: Name of the original volume
    :param new_name: Clone name
    :param pool_name: Name of the pool
    :param extra: Free-form string options
    :param dargs: Standardized virsh function API keywords
    :return: Returns the output of the command
    """
    cmd = "vol-clone --vol %s --newname %s %s" % (volume_name, new_name, extra)
    if pool_name:
        cmd += " --pool %s" % pool_name
    return command(cmd, **dargs)


def vol_wipe(volume_name, pool_name="", alg="", **dargs):
    """
    Ensure data previously on a volume is not accessible to future reads.

    :param volume_name: Name of the volume
    :param pool_name: Name of the pool
    :param alg: Perform selected wiping algorithm
    :param dargs: Standardized virsh function API keywords
    :return: Returns the output of the command
    """
    cmd = "vol-wipe --vol %s" % volume_name
    if pool_name:
        cmd += " --pool %s" % pool_name
    if alg:
        cmd += " --algorithm %s" % alg
    return command(cmd, **dargs)


def vol_resize(volume_name, capacity, pool_name="", extra="", **dargs):
    """
    Resizes a storage volume.

    :param volume_name: Name of the volume
    :param capacity: New capacity for the volume (default bytes)
    :param pool_name: Name of the pool
    :param extra: Free-form string options
    :param dargs: Standardized virsh function API keywords
    :return: Returns the output of the command
    """
    cmd = "vol-resize --vol %s --capacity %s " % (volume_name, capacity)
    if pool_name:
        cmd += " --pool %s " % pool_name
    if extra:
        cmd += extra
    return command(cmd, **dargs)


def capabilities(option='', to_file=None, **dargs):
    """
    Return output from virsh capabilities command

    :param option: additional options (takes none)
    :param dargs: standardized virsh function API keywords
    """
    cmd_result = command('capabilities %s' % option, **dargs)
    if to_file is not None:
        result_file = open(to_file, 'w')
        result_file.write(cmd_result.stdout.strip())
        result_file.close()

    return cmd_result.stdout_text.strip()


def pool_capabilities(option='', to_file=None, **dargs):
    """
    Return output from virsh pool-capabilities command

    :param option: additional options (takes none)
    :param to_file: file path for store capabilities' xml
    :param dargs: standardized virsh function API keywords
    """
    cmd_result = command('pool-capabilities %s' % option, **dargs)
    if to_file is not None:
        result_file = open(to_file, 'w')
        result_file.write(cmd_result.stdout.strip())
        result_file.close()
    return cmd_result.stdout_text.strip()


def nodecpustats(option='', **dargs):
    """
    Returns basic information about the node CPU statistics

    :param option: additional options (takes none)
    :param dargs: standardized virsh function API keywords
    """

    cmd_nodecpustat = "nodecpustats %s" % option
    return command(cmd_nodecpustat, **dargs)


def nodememstats(option='', **dargs):
    """
    Returns basic information about the node Memory statistics

    :param option: additional options (takes none)
    :param dargs: standardized virsh function API keywords
    """

    return command('nodememstats %s' % option, **dargs)


def memtune_set(name, options, **dargs):
    """
    Set the memory controller parameters

    :param domname: VM Name
    :param options: contains the values limit, state and value
    """
    return command("memtune %s %s" % (name, options), **dargs)


def memtune_list(name, **dargs):
    """
    List the memory controller value of a given domain

    :param domname: VM Name
    """
    return command("memtune %s" % (name), **dargs)


def memtune_get(name, key):
    """
    Get the specific memory controller value

    :param domname: VM Name
    :param key: memory controller limit for which the value needed
    :return: the memory value of a key in Kbs
    """
    memtune_output = memtune_list(name).stdout_text.strip()
    LOG.info("memtune output is %s" % memtune_output)
    memtune_value = re.findall(r"%s\s*:\s+(\S+)" % key, str(memtune_output))
    if memtune_value:
        return int(memtune_value[0] if memtune_value[0] != "unlimited" else -1)
    else:
        return -1


def help_command(options='', cache=False, **dargs):
    """
    Return list of commands and groups in help command output

    :param options: additional options to pass to help command
    :param cache: Return cached result if True, or refreshed cache if False
    :param dargs: standardized virsh function API keywords
    :return: List of command and group names
    """
    # Combine virsh command list and virsh group list.
    virsh_command_list = help_command_only(options, cache, **dargs)
    virsh_group_list = help_command_group(options, cache, **dargs)
    virsh_command_group = None
    virsh_command_group = virsh_command_list + virsh_group_list
    return virsh_command_group


def help_command_only(options='', cache=False, **dargs):
    """
    Return list of commands in help command output

    :param options: additional options to pass to help command
    :param cache: Return cached result if True, or refreshed cache if False
    :param dargs: standardized virsh function API keywords
    :return: List of command names
    """
    # global needed to support this function's use in Virsh method closure
    global VIRSH_COMMAND_CACHE
    if not VIRSH_COMMAND_CACHE or cache is False:
        VIRSH_COMMAND_CACHE = []
        regx_command_word = re.compile(r"\s+([a-z0-9-]+)\s+")
        result = help(options, **dargs)
        for line in result.stdout_text.strip().splitlines():
            # Get rid of 'keyword' line
            if line.find("keyword") != -1:
                continue
            mobj_command_word = regx_command_word.search(line)
            if mobj_command_word:
                VIRSH_COMMAND_CACHE.append(mobj_command_word.group(1))
    # Prevent accidental modification of cache itself
    return list(VIRSH_COMMAND_CACHE)


def help_command_group(options='', cache=False, **dargs):
    """
    Return list of groups in help command output

    :param options: additional options to pass to help command
    :param cache: Return cached result if True, or refreshed cache if False
    :param dargs: standardized virsh function API keywords
    :return: List of group names
    """
    # global needed to support this function's use in Virsh method closure
    global VIRSH_COMMAND_GROUP_CACHE, VIRSH_COMMAND_GROUP_CACHE_NO_DETAIL
    if VIRSH_COMMAND_GROUP_CACHE_NO_DETAIL:
        return []
    if not VIRSH_COMMAND_GROUP_CACHE or cache is False:
        VIRSH_COMMAND_GROUP_CACHE = []
        regx_group_word = re.compile(r"[\']([a-zA-Z0-9]+)[\']")
        result = help(options, **dargs)
        for line in result.stdout_text.strip().splitlines():
            # 'keyword' only exists in group line.
            if line.find("keyword") != -1:
                mojb_group_word = regx_group_word.search(line)
                if mojb_group_word:
                    VIRSH_COMMAND_GROUP_CACHE.append(mojb_group_word.group(1))
    if len(list(VIRSH_COMMAND_GROUP_CACHE)) == 0:
        VIRSH_COMMAND_GROUP_CACHE_NO_DETAIL = True
    # Prevent accidental modification of cache itself
    return list(VIRSH_COMMAND_GROUP_CACHE)


def has_help_command(virsh_cmd, options='', **dargs):
    """
    String match on virsh command in help output command list

    :param virsh_cmd: Name of virsh command or group to look for
    :param options: Additional options to send to help command
    :param dargs: standardized virsh function API keywords
    :return: True/False
    """
    return bool(help_command_only(options, cache=True,
                                  **dargs).count(virsh_cmd))


def has_command_help_match(virsh_cmd, regex, **dargs):
    """
    Regex search on subcommand help output

    :param virsh_cmd: Name of virsh command or group to match help output
    :param regex: regular expression string to match
    :param dargs: standardized virsh function API keywords
    :return: re match object
    """
    result = help(virsh_cmd, **dargs)
    command_help_output = result.stdout_text.strip()
    return re.search(regex, command_help_output)


def help(virsh_cmd='', **dargs):
    """
    Prints global help, command specific help, or help for a
    group of related commands

    :param virsh_cmd: Name of virsh command or group
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("help %s" % virsh_cmd, **dargs)


def schedinfo(domain, options="", **dargs):
    """
    Show/Set scheduler parameters.

    :param domain: vm's name id or uuid.
    :param options: additional options.
    :param dargs: standardized virsh function API keywords
    """
    cmd = "schedinfo %s %s" % (domain, options)
    return command(cmd, **dargs)


def setmem(domainarg=None, sizearg=None, domain=None,
           size=None, use_kilobytes=False, flagstr="", **dargs):
    """
    Change the current memory allocation in the guest domain.

    :param domainarg: Domain name (first pos. parameter)
    :param sizearg: Memory size in KiB (second. pos. parameter)
    :param domain: Option to --domain parameter
    :param size: Option to --size or --kilobytes parameter
    :param use_kilobytes: True for --kilobytes, False for --size
    :param dargs: standardized virsh function API keywords
    :param flagstr: string of "--config, --live, --current, etc."
    :return: CmdResult instance
    :raise: process.CmdError: if libvirtd is not running
    """

    cmd = "setmem"
    if domainarg is not None:  # Allow testing of ""
        cmd += " %s" % domainarg
    if domain is not None:  # Allow testing of --domain ""
        cmd += " --domain %s" % domain
    if sizearg is not None:  # Allow testing of 0 and ""
        cmd += " %s" % sizearg
    if size is not None:  # Allow testing of --size "" or --size 0
        if use_kilobytes:
            cmd += " --kilobytes %s" % size
        else:
            cmd += " --size %s" % size
    if len(flagstr) > 0:
        cmd += " %s" % flagstr
    return command(cmd, **dargs)


def setmaxmem(domainarg=None, sizearg=None, domain=None,
              size=None, use_kilobytes=False, flagstr="", **dargs):
    """
    Change the maximum memory allocation for the guest domain.

    :param domainarg: Domain name (first pos. parameter)
    :param sizearg: Memory size in KiB (second. pos. parameter)
    :param domain: Option to --domain parameter
    :param size: Option to --size or --kilobytes parameter
    :param use_kilobytes: True for --kilobytes, False for --size
    :param flagstr: string of "--config, --live, --current, etc."
    :return: CmdResult instance
    :raise: process.CmdError: if libvirtd is not running.
    """
    cmd = "setmaxmem"
    if domainarg is not None:  # Allow testing of ""
        cmd += " %s" % domainarg
    if sizearg is not None:  # Allow testing of 0 and ""
        cmd += " %s" % sizearg
    if domain is not None:  # Allow testing of --domain ""
        cmd += " --domain %s" % domain
    if size is not None:  # Allow testing of --size "" or --size 0
        if use_kilobytes:
            cmd += " --kilobytes %s" % size
        else:
            cmd += " --size %s" % size
    if len(flagstr) > 0:
        cmd += " %s" % flagstr
    return command(cmd, **dargs)


def set_user_password(domain=None, user=None, password=None,
                      encrypted=False, option=True, **dargs):
    """
    Set the user password inside the domain
    :param domain: Option to --domain parameter
    :param user: Option to --user parameter
    :param password: Option to --password
    :param encrypted: True for --encrypted
    :param option: True for --domain/user/password
    :return: CmdResult instance
    """
    cmd = "set-user-password"
    if option:
        if domain:
            cmd += " --domain %s" % domain
        if user:
            cmd += " --user %s" % user
        if password:
            cmd += " --password %s" % password
    else:
        if domain:
            cmd += " %s" % domain
        if user:
            cmd += " %s" % user
        if password:
            cmd += " %s" % password
    if encrypted:
        cmd += " --encrypted"
    return command(cmd, **dargs)


def snapshot_create(name, options="", **dargs):
    """
    Create snapshot of domain.

    :param name: name of domain
    :param dargs: standardized virsh function API keywords
    :return: name of snapshot
    """
    cmd = "snapshot-create %s %s" % (name, options)
    return command(cmd, **dargs)


def snapshot_edit(name, options="", **dargs):
    """
    Edit snapshot xml

    :param name: name of domain
    :param options: options of snapshot-edit command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "snapshot-edit %s %s" % (name, options)
    return command(cmd, **dargs)


def snapshot_create_as(name, options="", **dargs):
    """
    Create snapshot of domain with options.

    :param name: name of domain
    :param options: options of snapshot-create-as
    :param dargs: standardized virsh function API keywords
    :return: name of snapshot
    """
    # CmdResult is handled here, force ignore_status
    cmd = "snapshot-create-as %s" % name
    if options is not None:
        cmd += " %s" % options

    return command(cmd, **dargs)


def snapshot_parent(name, options, **dargs):
    """
    Get name of snapshot parent

    :param name: name of domain
    :param options: options of snapshot-parent
    :param dargs: standardized virsh function API keywords
    :return: name of snapshot
    """
    cmd = "snapshot-parent %s %s" % (name, options)
    return command(cmd, **dargs)


def snapshot_current(name, options="--name", **dargs):
    """
    Get name or xml of current snapshot.

    :param name: name of domain
    :param options: options of snapshot-current, default is --name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "snapshot-current %s" % name
    if options is not None:
        cmd += " %s" % options
    return command(cmd, **dargs)


def snapshot_list(name, options=None, **dargs):
    """
    Get list of snapshots of domain.

    :param name: name of domain
    :param options: options of snapshot_list
    :param dargs: standardized virsh function API keywords
    :return: list of snapshot names
    """
    # CmdResult is handled here, force ignore_status
    dargs['ignore_status'] = True
    ret = []
    cmd = "snapshot-list %s" % name
    if options is not None:
        cmd += " %s" % options

    sc_output = command(cmd, **dargs)
    if sc_output.exit_status != 0:
        raise process.CmdError(
            cmd, sc_output, "Failed to get list of snapshots")

    data = re.findall("\S* *\d*-\d*-\d* \d*:\d*:\d* [+-]\d* \w*",
                      sc_output.stdout_text)
    for rec in data:
        if not rec:
            continue
        ret.append(re.match("\S*", rec).group())

    return ret


def snapshot_dumpxml(name, snapshot, options=None, to_file=None, **dargs):
    """
    Get dumpxml of snapshot

    :param name: name of domain
    :param snapshot: name of snapshot
    :param options: options of snapshot_list
    :param to_file: optional file to write XML output to
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    cmd = "snapshot-dumpxml %s %s" % (name, snapshot)
    if options is not None:
        cmd += " %s" % options
    result = command(cmd, **dargs)
    if to_file is not None:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()

    return result


def snapshot_info(name, snapshot, **dargs):
    """
    Check snapshot information.

    :param name: name of domain
    :param snapshot: name os snapshot to verify
    :param dargs: standardized virsh function API keywords
    :return: snapshot information dictionary
    """
    # CmdResult is handled here, force ignore_status
    dargs['ignore_status'] = True
    ret = {}
    values = ["Name", "Domain", "Current", "State", "Parent",
              "Children", "Descendants", "Metadata"]

    cmd = "snapshot-info %s %s" % (name, snapshot)
    sc_output = command(cmd, **dargs)
    if sc_output.exit_status != 0:
        raise process.CmdError(cmd, sc_output, "Failed to get snapshot info")

    for val in values:
        data = re.search("(?<=%s:) *(\w.*|\w*)" % val,
                         sc_output.stdout_text)
        if data is None:
            continue
        ret[val] = data.group(0).strip()

    if ret["Parent"] == "":
        ret["Parent"] = None

    return ret


def snapshot_revert(name, snapshot, options="", **dargs):
    """
    Revert domain state to saved snapshot.

    :param name: name of domain
    :param dargs: standardized virsh function API keywords
    :param snapshot: snapshot to revert to
    :return: CmdResult instance
    """
    cmd = "snapshot-revert %s %s %s" % (name, snapshot, options)
    return command(cmd, **dargs)


def snapshot_delete(name, snapshot, options='', **dargs):
    """
    Remove domain snapshot

    :param name: name of domain
    :param dargs: standardized virsh function API keywords
    :param snapshot: snapshot to delete
    :return: CmdResult instance
    """
    cmd = "snapshot-delete %s %s %s" % (name, snapshot, options)
    return command(cmd, **dargs)


def blockcommit(name, path, options="", **dargs):
    """
    Start a block commit operation.

    :param name: name of domain
    :param options: options of blockcommit
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "blockcommit %s %s" % (name, path)
    if options is not None:
        cmd += " %s" % options

    return command(cmd, **dargs)


def blockpull(name, path, options="", **dargs):
    """
    Start a block pull operation.

    :param name: name of domain
    :param options: options of blockpull
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "blockpull %s %s" % (name, path)
    if options is not None:
        cmd += " %s" % options

    return command(cmd, **dargs)


def blockresize(name, path, size, **dargs):
    """
    Resize block device of domain.

    :param name: name of domain
    :param path: path of block device
    :size: new size of the block device
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("blockresize %s %s %s" % (name, path, size), **dargs)


def domblkinfo(name, device, **dargs):
    """
    Get block device size info for a domain.

    :param name: VM's name or id,uuid.
    :param device: device of VM.
    :param dargs: standardized virsh function API keywords.
    :return: CmdResult object.
    """
    return command("domblkinfo %s %s" % (name, device), **dargs)


def domblklist(name, options=None, **dargs):
    """
    Get domain devices.

    :param name: name of domain
    :param options: options of domblklist.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "domblklist %s" % name
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def domiflist(name, options='', extra='', **dargs):
    """
    Get the domain network devices

    :param name: name of domain
    :param options: options of domiflist
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """

    return command('domiflist %s %s %s' % (name, options, extra), **dargs)


def cpu_stats(name, options, **dargs):
    """
    Display per-CPU and total statistics about domain's CPUs

    :param name: name of domain
    :param options: options of cpu_stats
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "cpu-stats %s" % name
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


@EventTracker.wait_event
def change_media(name, device, options, wait_for_event=False,
                 event_type='tray-change', event_timeout=7, **dargs):
    """
    Change media of CD or floppy drive.

    :param name: VM's name.
    :param path: Fully-qualified path or target of disk device
    :param options: command change_media options.
    :param wait_for_event: wait until device_change event comes
    :param event_type: type of the event
    :param event_timeout: timeout for virsh event command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "change-media %s %s " % (name, device)
    if options:
        cmd += " %s " % options
    return command(cmd, **dargs)


def cpu_compare(xml_file, **dargs):
    """
    Compare host CPU with a CPU described by an XML file

    :param xml_file: file containing an XML CPU description.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("cpu-compare %s" % xml_file, **dargs)


def hypervisor_cpu_compare(xml_file, options="", **dargs):
    """
    Compare CPU provided by hypervisor on the host with a CPU
    described by an XML file

    :param xml_file: file containing an XML CPU description
    :param options: extra options passed to virsh command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("hypervisor-cpu-compare %s %s" % (xml_file, options),
                   **dargs)


def hypervisor_cpu_baseline(xml_file, options="", **dargs):
    """
    Compute baseline CPU for a set of given CPUs with the CPU the hypervisor
    is able to provide on the host

    :param xml_file: file containing an XML CPU description.
    :param options: extra options passed to virsh command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("hypervisor-cpu-baseline %s %s" % (xml_file, options),
                   **dargs)


def cpu_baseline(xml_file, **dargs):
    """
    Compute baseline CPU for a set of given CPUs.

    :param xml_file: file containing an XML CPU description.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("cpu-baseline %s" % xml_file, **dargs)


def numatune(name, mode=None, nodeset=None, options=None, **dargs):
    """
    Set or get a domain's numa parameters
    :param name: name of domain
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "numatune %s" % name
    if options:
        cmd += " --%s" % options
    if mode:
        cmd += " --mode %s" % mode
    if nodeset:
        cmd += " --nodeset %s" % nodeset

    return command(cmd, **dargs)


def nodedev_reset(name, options="", **dargs):
    """
    Trigger a device reset for device node.

    :param name: device node name to be reset.
    :param options: additional options passed to virsh command
    :param dargs: standardized virsh function API keywords
    :return: cmdresult object.
    """
    cmd = ("nodedev-reset --device %s %s" % (name, options))
    return command(cmd, **dargs)


def ttyconsole(name, **dargs):
    """
    Print tty console device.

    :param name: name, uuid or id of domain
    :return: CmdResult instance
    """
    return command("ttyconsole %s" % name, **dargs)


def nodedev_dumpxml(name, options="", to_file=None, **dargs):
    """
    Do dumpxml for node device.

    :param name: the name of device.
    :param options: extra options to nodedev-dumpxml cmd.
    :param to_file: optional file to write XML output to.

    :return: Cmdobject of virsh nodedev-dumpxml.
    """
    cmd = ('nodedev-dumpxml %s %s' % (name, options))
    result = command(cmd, **dargs)
    if to_file is not None:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()

    return result


def connect(connect_uri="", options="", **dargs):
    """
    Run a connect command to the uri.

    :param connect_uri: target uri connect to.
    :param options: options to pass to connect command
    :return: CmdResult object.
    """
    return command("connect %s %s" % (connect_uri, options), **dargs)


def domif_setlink(name, interface, state, options=None, **dargs):
    """
    Set network interface stats for a running domain.

    :param name: Name of domain
    :param interface: interface device
    :param state: new state of the device  up or down
    :param options: command options.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "domif-setlink %s %s %s " % (name, interface, state)
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def domif_getlink(name, interface, options=None, **dargs):
    """
    Get network interface stats for a running domain.

    :param name: Name of domain
    :param interface: interface device
    :param options: command options.
    :param dargs: standardized virsh function API keywords
    :return: domif state
    """
    cmd = "domif-getlink %s %s " % (name, interface)
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def nodedev_list(tree=False, cap="", options="", **dargs):
    """
    List the node devices.

    :param tree: list devices in a tree
    :param cap: capability names, separated by comma
    :param options: extra command options.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """
    cmd = "nodedev-list"
    if tree:
        cmd += " --tree"
    if cap:
        cmd += " --cap %s" % cap
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def nodedev_detach(name, options="", **dargs):
    """
    Detach node device from host.

    :return: cmdresult object.
    """
    cmd = ("nodedev-detach --device %s %s" % (name, options))
    return command(cmd, **dargs)


def nodedev_dettach(name, options="", **dargs):
    """
    Detach node device from host.

    :return: nodedev_detach(name).
    """
    return nodedev_detach(name, options, **dargs)


def nodedev_reattach(name, options="", **dargs):
    """
    If node device is detached, this action will
    reattach it to its device driver.

    :return: cmdresult object.
    """
    cmd = ("nodedev-reattach --device %s %s" % (name, options))
    return command(cmd, **dargs)


def vcpucount(name, options="", **dargs):
    """
    Get the vcpu count of guest.

    :param name: name of domain.
    :param options: options for vcpucoutn command.
    :return: CmdResult object.
    """
    cmd = "vcpucount %s %s" % (name, options)
    return command(cmd, **dargs)


def blockcopy(name, path, dest, options="", **dargs):
    """
    Start a block copy operation.

    :param name: name of domain.
    :param path: fully-qualified path or target of disk.
    :param dest: path of the copy to create.
    :param options: options of blockcopy.
    :param dargs: standardized virsh function API keywords.
    :return: CmdResult instance.
    """
    cmd = "blockcopy %s %s %s %s" % (name, path, dest, options)
    return command(cmd, **dargs)


def blockjob(name, path, options="", **dargs):
    """
    Manage active block operations.

    :param name: name of domain.
    :param path: fully-qualified path or target of disk.
    :param options: options of blockjob.
    :param dargs: standardized virsh function API keywords.
    :return: CmdResult instance.
    """
    cmd = "blockjob %s %s %s" % (name, path, options)
    return command(cmd, **dargs)


def domiftune(name, interface, options=None, inbound=None,
              outbound=None, **dargs):
    """
    Set/get parameters of a virtual interface.

    :param name: name of domain.
    :param interface: interface device (MAC Address).
    :param inbound: control domain's incoming traffics.
    :param outbound: control domain's outgoing traffics.
    :param options: options may be live, config and current.
    :param dargs: standardized virsh function API keywords.
    :return: CmdResult instance.
    """
    cmd = "domiftune %s %s" % (name, interface)
    if inbound:
        cmd += "  --inbound %s" % inbound
    if outbound:
        cmd += "  --outbound %s" % outbound
    if options:
        cmd += " --%s" % options
    return command(cmd, **dargs)


def desc(name, options, desc_str, **dargs):
    """
    Show or modify description or title of a domain.

    :param name: name of domain.
    :param options: options for desc command.
    :param desc_str: new desc message.
    :param dargs: standardized virsh function API keywords.
    :return: CmdResult object.
    """
    if desc_str:
        options = options + " \"%s\"" % desc_str
    cmd = "desc %s %s" % (name, options)
    return command(cmd, **dargs)


def allocpages(size, count, extra=None, **dargs):
    """
    Set the number of hugepages for specific size.

    :param size: Hugepage size
    :param count: Number of pages to set
    :param extra: additional arguments for the virsh command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "allocpages %s %s" % (size, count)
    if extra:
        cmd = cmd + " %s" % extra
    return command(cmd, **dargs)


def autostart(name, options, **dargs):
    """
    Autostart a domain

    :return: cmdresult object.
    """
    cmd = ("autostart %s %s" % (name, options))
    return command(cmd, **dargs)


def node_memtune(shm_pages_to_scan=None, shm_sleep_millisecs=None,
                 shm_merge_across_nodes=None, options=None, **dargs):
    """
    Get or set node memory parameters.

    :param options: Extra options to virsh.
    :param shm-pages-to-scan: Pages to scan.
    :param shm-sleep-millisecs: Sleep time (ms).
    :param shm-merge-across-nodes: Merge across nodes.
    :param dargs: Standardized virsh function API keywords.
    :return: CmdResult instance
    """
    cmd = "node-memory-tune"
    if shm_pages_to_scan:
        cmd += " --shm-pages-to-scan %s" % shm_pages_to_scan
    if shm_sleep_millisecs:
        cmd += " --shm-sleep-millisecs %s" % shm_sleep_millisecs
    if shm_merge_across_nodes:
        cmd += " --shm-merge-across-nodes %s" % shm_merge_across_nodes
    if options:
        cmd += " --%s" % options

    return command(cmd, **dargs)


def iface_list(extra="", **dargs):
    """
    List physical host interfaces.

    :param extra: Free-form string of options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-list %s" % extra, **dargs)


def iface_define(xml_path, **dargs):
    """
    Define (but don't start) a physical host interface from an XML file.

    :param xml_path: XML file path
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-define --file %s" % xml_path, **dargs)


def iface_start(iface, **dargs):
    """
    Start a physical host interface.

    :param iface: Interface name or MAC address
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-start %s" % iface, **dargs)


def iface_destroy(iface, **dargs):
    """
    Destroy a physical host interface.

    :param iface: Interface name or MAC address
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-destroy %s" % iface, **dargs)


def iface_undefine(iface, **dargs):
    """
    Undefine a physical host interface (remove it from configuration).

    :param iface: Interface name or MAC address
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-undefine %s" % iface, **dargs)


def iface_dumpxml(iface, extra="", to_file="", **dargs):
    """
    Interface information in XML.

    :param iface: Interface name or MAC address
    :param extra: Free-form string of options
    :param to_file: Optional file to write xml
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    dargs['ignore_status'] = True
    cmd = "iface-dumpxml %s %s" % (iface, extra)
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    if result.exit_status:
        raise process.CmdError(cmd, result,
                               "Dumpxml returned non-zero exit status")
    return result.stdout_text.strip()


def iface_name(mac, **dargs):
    """
    Convert an interface MAC address to interface name.

    :param mac: Interface MAC address
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-name %s" % mac, **dargs)


def iface_mac(name, **dargs):
    """
    Convert an interface name to interface MAC address.

    :param name: Interface name
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-mac %s" % name, **dargs)


def iface_edit(iface, **dargs):
    """
    Edit XML configuration for a physical host interface.

    :param iface: Interface name or MAC address
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-edit %s" % iface, **dargs)


def iface_bridge(iface, bridge, extra="", **dargs):
    """
    Create a bridge device and attach an existing network device to it.

    :param iface: Interface name or MAC address
    :param bridge: New bridge device name
    :param extra: Free-form string of options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-bridge %s %s %s" % (iface, bridge, extra), **dargs)


def iface_unbridge(bridge, extra="", **dargs):
    """
    Undefine a bridge device after detaching its slave device.

    :param bridge: Current bridge device name
    :param extra: Free-form string of options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult object
    """
    return command("iface-unbridge %s %s" % (bridge, extra), **dargs)


def iface_begin(**dargs):
    """
    Create a snapshot of current interfaces settings

    :param: dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("iface-begin", **dargs)


def iface_commit(**dargs):
    """
    Commit changes made since iface-begin and free restore point

    :param: dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("iface-commit", **dargs)


def iface_rollback(**dargs):
    """
    Rollback to previous saved configuration created via iface-begin

    :param: dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    return command("iface-rollback", **dargs)


def emulatorpin(name, cpulist=None, options=None, **dargs):
    """
    Control or query domain emulator affinity
    :param name: name of domain
    :param cpulist: a list of physical CPU numbers
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "emulatorpin %s" % name
    if options:
        cmd += " --%s" % options
    if cpulist:
        cmd += " --cpulist %s" % cpulist

    return command(cmd, **dargs)


def secret_list(options="", **dargs):
    """
    Get list of secret.

    :param options: the option may be '--ephemeral'
    :param dargs: standardized virsh function API keywords
    :return: list of secret
    """
    # CmdResult is handled here, force ignore_status
    cmd = "secret-list %s" % options
    return command(cmd, **dargs)


def secret_define(xml_file, options=None, **dargs):
    """
    Return cmd result of secret define.

    :param xml_file: secret XML file
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "secret-define --file %s" % xml_file
    if options is not None:
        cmd += " %s" % options
    LOG.debug("Define secret from %s", xml_file)
    return command(cmd, **dargs)


def secret_undefine(uuid, options=None, **dargs):
    """
    Return cmd result of secret undefine.

    :param uuid: secret UUID
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "secret-undefine %s" % uuid
    if options is not None:
        cmd += " %s" % options

    LOG.debug("Undefine secret %s", uuid)
    return command(cmd, **dargs)


def secret_dumpxml(uuid, to_file="", options=None, **dargs):
    """
    Return the secret information as an XML dump.

    :param uuid: secret UUID
    :param to_file: optional file to write XML output to
    :param dargs: standardized virsh function API keywords
    :return: standard output from command
    """
    dargs['ignore_status'] = True
    cmd = "secret-dumpxml %s" % uuid
    if options is not None:
        cmd += " %s" % options
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    if result.exit_status:
        raise process.CmdError(cmd, result,
                               "Virsh secret-dumpxml returned \
                             non-zero exit status")
    return result


def secret_get_value(uuid, options=None, **dargs):
    """
    Get a secret value

    :param uuid: secret UUID
    :return: CmdResult object.
    """
    cmd = "secret-get-value --secret %s" % uuid
    if options:
        cmd += " --%s" % options

    return command(cmd, **dargs)


def secret_set_value(uuid, password, options=None, encode=False, use_file=False, **dargs):
    """
    Set a secret value

    :param uuid: secret UUID
    :param password: secret value
    :param encode: if False, that means you've already provided a base64-encoded
                   password. if True, will base64-encode password before use it.
    :param use_file: allow choose new --file option, but default is false
    :return: CmdResult object.
    """
    cmd = "secret-set-value --secret %s" % uuid
    if password:
        if encode:
            encoding = locale.getpreferredencoding()
            password = base64.b64encode(password.encode(encoding)).decode(encoding)
        # as per https://bugzilla.redhat.com/show_bug.cgi?id=1826636,
        # virsh secret-set-value will throw error if pass secret value by --base64 option
        # Read the secret from a file is right choice.
        if use_file:
            secret_file = os.path.join(data_dir.get_tmp_dir(), "secret_file")
            with open(secret_file, 'w+') as fd:
                fd.write(password)
            cmd += " --file %s" % secret_file
        else:
            cmd += " --base64 %s" % password
    if options:
        cmd += " --%s" % options

    return command(cmd, **dargs)


def nodedev_create(xml_file, options=None, **dargs):
    """
    Return cmd result of the device to be created by an XML file

    :param xml_file: device XML file
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nodedev-create %s" % xml_file
    if options is not None:
        cmd += " %s" % options

    LOG.debug("Create the device from %s", xml_file)
    return command(cmd, **dargs)


def nodedev_destroy(dev_name, options=None, **dargs):
    """
    Return cmd result of the device to be destroyed

    :param dev_name: name of the device
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nodedev-destroy %s" % dev_name
    if options is not None:
        cmd += " %s" % options

    LOG.debug("Destroy the device %s on the node", dev_name)
    return command(cmd, **dargs)


def domfstrim(name, minimum=None, mountpoint=None, options="", **dargs):
    """
    Do fstrim on domain's mounted filesystems

    :param name: name of domain
    :param options: options maybe --minimum <number>, --mountpoint <string>
    :return: CmdResult object
    """
    cmd = "domfstrim %s" % name
    if minimum is not None:
        cmd += " --minimum %s" % minimum
    if mountpoint is not None:
        cmd += " --mountpoint %s" % mountpoint

    cmd += " %s" % options
    return command(cmd, **dargs)


def domfsfreeze(name, mountpoint=None, options="", **dargs):
    """
    Freeze domain's mounted filesystems

    :param name: name of domain
    :param mountpoint: specific mountpoints to be frozen
    :param options: extra options to domfsfreeze cmd.
    :return: CmdResult object
    """
    cmd = "domfsfreeze %s" % name
    if mountpoint is not None:
        cmd += " --mountpoint %s" % mountpoint

    cmd += " %s" % options
    return command(cmd, **dargs)


def domfsthaw(name, mountpoint=None, options="", **dargs):
    """
    Thaw domain's mounted filesystems

    :param name: name of domain
    :param mountpoint: specific mountpoints to be thawed
    :param options: extra options to domfsfreeze cmd.
    :return: CmdResult object
    """
    cmd = "domfsthaw %s" % name
    if mountpoint is not None:
        cmd += " --mountpoint %s" % mountpoint

    cmd += " %s" % options
    return command(cmd, **dargs)


def domtime(name, now=False, pretty=False, sync=False, time=None,
            options="", **dargs):
    """
    Get/Set domain's time

    :param name: name of domain
    :param now: set to the time of the host running virsh
    :param pretty: print domain's time in human readable form
    :param sync: instead of setting given time, synchronize from domain's RTC
    :param time: integer time to set
    :return: CmdResult object
    """
    cmd = "domtime %s" % name
    if now:
        cmd += " --now"
    if pretty:
        cmd += " --pretty"
    if sync:
        cmd += " --sync"
    if time is not None:
        cmd += " --time %s" % time

    cmd += " %s" % options
    return command(cmd, **dargs)


def nwfilter_dumpxml(name, options="", to_file=None, **dargs):
    """
    Do dumpxml for network filter.

    :param name: the name or uuid of filter.
    :param options: extra options to nwfilter-dumpxml cmd.
    :param to_file: optional file to write XML output to.
    :param dargs: standardized virsh function API keywords
    :return: Cmdobject of virsh nwfilter-dumpxml.
    """
    cmd = ('nwfilter-dumpxml %s %s' % (name, options))
    result = command(cmd, **dargs)
    if to_file is not None:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()

    return result


def nwfilter_define(xml_file, options="", **dargs):
    """
    Return cmd result of network filter define.

    :param xml_file: network filter XML file
    :param options: extra options to nwfilter-define cmd.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nwfilter-define --file %s %s" % (xml_file, options)
    return command(cmd, **dargs)


def nwfilter_undefine(name, options="", **dargs):
    """
    Return cmd result of network filter undefine.

    :param name: network filter name or uuid
    :param options: extra options to nwfilter-undefine cmd.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nwfilter-undefine %s %s" % (name, options)
    return command(cmd, **dargs)


def nwfilter_list(options="", **dargs):
    """
    Get list of network filters.

    :param options: extra options
    :param dargs: standardized virsh function API keywords
    :return: list of network filters
    """
    cmd = "nwfilter-list %s" % options
    return command(cmd, **dargs)


def nwfilter_edit(name, options="", **dargs):
    """
    Edit the XML configuration for a network filter.

    :param name: network filter name or uuid.
    :param options: extra options to nwfilter-edit cmd.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nwfilter-edit %s %s" % (name, options)
    return command(cmd, **dargs)


def nwfilter_binding_create(name, options="", **dargs):
    """
    Associate a network port with a network filter.
    The network filter backend will immediately
    attempt to instantiate the filter rules on the
    port.

    :param name: binding xml file name
    :param options: extra options to nwfilter-binding- cmd.
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "nwfilter-binding-create %s %s" % (name, options)
    return command(cmd, **dargs)


def nwfilter_binding_list(options="", **dargs):
    """
    List all of the network ports which have filters
    associated with them

    :param options: extra options for nwfilter_binding_list
    :param dargs: standardized virsh function API keywords
    """
    cmd = "nwfilter-binding-list %s" % options
    return command(cmd, **dargs)


def nwfilter_binding_dumpxml(portdev_name, options="", to_file="", **dargs):
    """
    output the network filter binding XML for network device
    called port name

    :param portdev_name: port device name for nwfilter_binding_dumpxml
    :param options: extra options for nwfilter_binding_dumpxml
    :param dargs: standardized virsh function API keywords
    """
    cmd = "nwfilter-binding-dumpxml %s %s" % (portdev_name, options)
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    return result


def nwfilter_binding_delete(portdev_name, option="", **dargs):
    """
    Disassociate a network port from a network filter.
    The network filter backend will immediately
    tear down the filter rules that exist on the port

    :param portdev_name: port device name for nwfilter_binding_delete
    :param option: extra option for nwfilter_binding_delete
    """
    cmd = "nwfilter-binding-delete %s %s" % (portdev_name, option)
    return command(cmd, **dargs)


def cd(dir_path, options="", **dargs):
    """
    Run cd command in virsh interactive session.

    :param dir_path: dir path string
    :param options: extra options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "cd --dir %s %s" % (dir_path, options)
    return command(cmd, **dargs)


def pwd(options="", **dargs):
    """
    Run pwd command in virsh session.

    :param options: extra options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "pwd %s" % options
    return command(cmd, **dargs)


def echo(echo_str, options="", **dargs):
    """
    Run echo command in virsh session.

    :param echo_str: the echo string
    :param options: extra options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "echo %s %s" % (echo_str, options)
    return command(cmd, **dargs)


def exit(**dargs):
    """
    Run exit command in virsh session.

    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "exit"
    return command(cmd, **dargs)


def quit(**dargs):
    """
    Run quit command in virsh session.

    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "quit"
    return command(cmd, **dargs)


def sendkey(name, keycode, codeset="", holdtime="", **dargs):
    """
    Send keycodes to the guest
    :param name: name of domain
    :param keycode: the key code
    :param codeset: the codeset of keycodes
    :param holdtime: milliseconds for each keystroke to be held
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "send-key %s" % name
    if codeset:
        cmd += " --codeset %s" % codeset
    if holdtime:
        cmd += " --holdtime %s" % holdtime
    cmd += " %s" % keycode
    return command(cmd, **dargs)


def create(xmlfile, options="", **dargs):
    """
    Create guest from xml

    :param xmlfile: domain xml file
    :param options: --paused
    :return: CmdResult object
    """
    cmd = "create %s %s" % (xmlfile, options)
    return command(cmd, **dargs)


def sysinfo(options="", **dargs):
    """
    Return the hypervisor sysinfo xml.

    :param options: extra options
    :return: CmdResult object
    """
    cmd = "sysinfo %s" % options
    return command(cmd, **dargs)


def reset(name, **dargs):
    """
    Reset a domain

    :param name: name of domain
    :return: CmdResult object
    """
    cmd = "reset %s" % name
    return command(cmd, **dargs)


def domdisplay(name, options="", **dargs):
    """
    Get domain display connection URI

    :param name: name of domain
    :param options: options of domdisplay
    :return: CmdResult object
    """
    cmd = "domdisplay %s %s" % (name, options)
    return command(cmd, **dargs)


def domblkerror(name, **dargs):
    """
    Show errors on block devices

    :param name: name of domain
    :return: CmdResult object
    """
    return command("domblkerror %s" % name, **dargs)


def domcontrol(name, options="", **dargs):
    """
    Return domain control interface state.

    :param name: name of domain
    :param options: extra options
    :return: CmdResult object
    """
    cmd = "domcontrol %s %s" % (name, options)
    return command(cmd, **dargs)


def save_image_dumpxml(state_file, options="", to_file="", **dargs):
    """
    Dump xml from saved state file

    :param state_file: saved state file to read
    :param options: extra options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "save-image-dumpxml %s %s" % (state_file, options)
    result = command(cmd, **dargs)
    if to_file:
        result_file = open(to_file, 'w')
        result_file.write(result.stdout.strip())
        result_file.close()
    return result


def save_image_define(state_file, xmlfile, options="", **dargs):
    """
    Redefine the XML for a domain's saved state file

    :param state_file: saved state file to modify
    :param xmlfile: filename containing updated XML for the target
    :param options: extra options
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "save-image-define %s %s %s" % (state_file, xmlfile, options)
    return command(cmd, **dargs)


def inject_nmi(name, options="", **dargs):
    """
    Inject NMI to the guest

    :param name: domain name
    :param options: extra options
    """
    cmd = "inject-nmi %s %s" % (name, options)
    return command(cmd, **dargs)


def vol_download(name, dfile, options="", **dargs):
    """
    Download volume contents to a file

    :param name: name of volume
    :param dfile: file path that will download to
    :param options: pool name, offset and length
    :return: CmdResult object
    """
    cmd = "vol-download %s %s %s" % (name, dfile, options)
    return command(cmd, **dargs)


def vol_upload(name, dfile, options="", **dargs):
    """
    Upload file contents to a volume

    :param name: name of volume
    :param dfile: file path that will upload from
    :param options: pool name, offset and length
    :return: CmdResult object
    """
    cmd = "vol-upload %s %s %s" % (name, dfile, options)
    return command(cmd, **dargs)


def blkiotune(name, weight=None, device_weights=None, device_read_iops_sec=None,
              device_write_iops_sec=None, device_read_bytes_sec=None,
              device_write_bytes_sec=None, options=None, **dargs):
    """
    Set or get a domain's blkio parameters
    :param name: name of domain
    :param weight: overall blkio weight
    :param device_weights: blkio weight for specific dev
    :param device_read_iops_sec: read iops for specific dev
    :param device_write_iops_sec: write iops for specific dev
    :param device_read_bytes_sec: read bytes per sec for specific dev
    :param device_write_bytes_sec: write bytes per sec for specific dev
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "blkiotune %s" % name
    if options:
        cmd += " --%s" % options
    if weight:
        cmd += " --weight %s" % weight
    if device_weights:
        cmd += " --device-weights %s" % device_weights
    if device_read_iops_sec:
        cmd += " --device-read-iops-sec %s" % device_read_iops_sec
    if device_write_iops_sec:
        cmd += " --device-write-iops-sec %s" % device_write_iops_sec
    if device_read_bytes_sec:
        cmd += " --device-read-bytes-sec %s" % device_read_bytes_sec
    if device_write_bytes_sec:
        cmd += " --device-write-bytes-sec %s" % device_write_bytes_sec

    return command(cmd, **dargs)


def blkdeviotune(name, device=None, options=None, params=None, **dargs):
    """
    Set or get a domain's blkio parameters
    :param name: name of domain
    :param device: device name may be vda, vdb and so on
    :param options: options may be live, config and current
    :param params: parameters for blkdeviotune
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "blkdeviotune %s" % name
    if options:
        cmd += " %s" % options
    if device:
        cmd += " --device %s" % device
    if params:
        if params.get("total_iops_sec"):
            cmd += " --total-iops-sec %s" % params.get("total_iops_sec")
        if params.get("read_iops_sec"):
            cmd += " --read-iops-sec %s" % params.get("read_iops_sec")
        if params.get("write_iops_sec"):
            cmd += " --write-iops-sec %s" % params.get("write_iops_sec")
        if params.get("total_iops_sec_max"):
            cmd += " --total-iops-sec-max %s" % params.get("total_iops_sec_max")
        if params.get("read_iops_sec_max"):
            cmd += " --read-iops-sec-max %s" % params.get("read_iops_sec_max")
        if params.get("write_iops_sec_max"):
            cmd += " --write-iops-sec-max %s" % params.get("write_iops_sec_max")
        if params.get("total_iops_sec_max_length"):
            cmd += " --total-iops-sec-max-length %s" % params.get("total_iops_sec_max_length")
        if params.get("read_iops_sec_max_length"):
            cmd += " --read-iops-sec-max-length %s" % params.get("read_iops_sec_max_length")
        if params.get("write_iops_sec_max_length"):
            cmd += " --write-iops-sec-max-length %s" % params.get("write_iops_sec_max_length")
        if params.get("total_bytes_sec"):
            cmd += " --total-bytes-sec %s" % params.get("total_bytes_sec")
        if params.get("read_bytes_sec"):
            cmd += " --read-bytes-sec %s" % params.get("read_bytes_sec")
        if params.get("write_bytes_sec"):
            cmd += " --write-bytes-sec %s" % params.get("write_bytes_sec")
        if params.get("total_bytes_sec_max"):
            cmd += " --total-bytes-sec-max %s" % params.get("total_bytes_sec_max")
        if params.get("read_bytes_sec_max"):
            cmd += " --read-bytes-sec-max %s" % params.get("read_bytes_sec_max")
        if params.get("write_bytes_sec_max"):
            cmd += " --write-bytes-sec-max %s" % params.get("write_bytes_sec_max")
        if params.get("total_bytes_sec_max_length"):
            cmd += " --total-bytes-sec-max %s" % params.get("total_bytes_sec_max_length")
        if params.get("read_bytes_sec_max_length"):
            cmd += " --read-bytes-sec-max-length %s" % params.get("read_bytes_sec_max_length")
        if params.get("write_bytes_sec_max_length"):
            cmd += " --write-bytes-sec-max-length %s" % params.get("write_bytes_sec_max_length")
        if params.get("size_iops_sec"):
            cmd += " --size-iops-sec %s" % params.get("size_iops_sec")
        if params.get("group_name"):
            cmd += " --group-name %s" % params.get("group_name")
    return command(cmd, **dargs)


def perf(domain, options="", events="", other_opt="", **dargs):
    """
    Enable or disable perf events

    :param domain: Domain name, id
    :param options: --enable | --disable
    :param events: perf event names separated by comma
    :param other_opt: --config | --live | --current
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """

    cmd = "perf %s %s %s %s" % (domain, options, events, other_opt)
    return command(cmd, **dargs)


def domstats(domains="", options="", **dargs):
    """
    Get statistics about one or multiple domains

    :param domains: List of domains
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "domstats %s %s" % (domains, options)
    return command(cmd, **dargs)


def freepages(cellno=None, pagesize=None, options="", **dargs):
    """
    Display available free pages for the NUMA cell

    :param cellno: NUMA cell number
    :param pagesize: Page size (in kibibytes)
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "freepages %s" % options
    if cellno is not None:
        cmd += " --cellno %s" % cellno
    if pagesize is not None:
        cmd += " --pagesize %s" % pagesize
    return command(cmd, **dargs)


def domcapabilities(virttype=None, emulatorbin=None, arch=None, machine=None,
                    options="", **dargs):
    """
    Capabilities of emulator with respect to host and libvirt

    :param virttype: Virtualization type (/domain/@type)
    :param emulatorbin: Path to emulator binary (/domain/devices/emulator)
    :param arch: Domain architecture (/domain/os/type/@arch)
    :param machine: machine type (/domain/os/type/@machine)
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "domcapabilities %s" % options
    if virttype:
        cmd += " --virttype %s" % virttype
    if emulatorbin:
        cmd += " --emulatorbin %s" % emulatorbin
    if arch:
        cmd += " --arch %s" % arch
    if machine:
        cmd += " --machine %s" % machine
    return command(cmd, **dargs)


def metadata(name, uri, options="", key=None, new_metadata=None, **dargs):
    """
    Show or set domain's custom XML Metadata

    :param name: Domain name, id or uuid
    :param uri: URI of the namespace
    :param options: options may be live, config and current
    :param key: Key to be used as a namespace identifier
    :param new_metadata: new metadata to set
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "metadata --domain %s --uri %s %s" % (name, uri, options)
    if key:
        cmd += " --key %s" % key
    if new_metadata:
        cmd += " --set '%s'" % new_metadata.replace("\'", "\"")
    return command(cmd, **dargs)


def cpu_models(arch, options="", **dargs):
    """
    Get the CPU models for an arch.

    :param arch: Architecture
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "cpu-models %s %s" % (arch, options)
    return command(cmd, **dargs)


def net_dhcp_leases(network, mac=None, options="", **dargs):
    """
    Print lease info for a given network

    :param network: Network name or uuid
    :param mac: Mac address
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "net-dhcp-leases %s %s" % (network, options)
    if mac:
        cmd += " --mac %s" % mac
    return command(cmd, **dargs)


def qemu_monitor_event(domain=None, event=None, event_timeout=None,
                       options="", **dargs):
    """
    Listen for QEMU Monitor Events

    :param domain: Domain name, id or UUID
    :param event: Event type name
    :param event_timeout: Timeout seconds
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "qemu-monitor-event %s" % options
    if domain:
        cmd += " --domain %s" % domain
    if event:
        cmd += " --event %s" % event
    if event_timeout:
        cmd += " --timeout %s" % event_timeout
    return command(cmd, **dargs)


def net_event(network=None, event=None, event_timeout=None, options="",
              **dargs):
    """
    List event types, or wait for network events to occur

    :param network: Network name or uuid
    :param event: Event type to wait for
    :param event_timeout: Timeout seconds
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "net-event %s" % options
    if network:
        cmd += " --network %s" % network
    if event:
        cmd += " --event %s" % event
    if event_timeout:
        cmd += " --timeout %s" % event_timeout
    return command(cmd, **dargs)


def event(domain=None, event=None, event_timeout=None, options="", **dargs):
    """
    List event types, or wait for domain events to occur

    :param domain: Domain name, id or UUID
    :param event: Event type name
    :param event_timeout: Timeout seconds
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "event %s" % options
    if domain:
        cmd += " --domain %s" % domain
    if event:
        cmd += " --event %s" % event
    if event_timeout:
        cmd += " --timeout %s" % event_timeout
    return command(cmd, **dargs)


def move_mouse(name, coordinate, **dargs):
    """
    Move VM mouse.

    :param name: domain name
    :param coordinate: Mouse coordinate
    """
    cmd = "mouse_move %s %s" % coordinate
    qemu_monitor_command(name=name, cmd=cmd, options='--hmp', **dargs)
    # Sleep 1 sec to make sure VM received mouse move event
    time.sleep(1)


def click_button(name, left_button=True, **dargs):
    """
    Click left/right button of VM mouse.

    :param name: domain name
    :param left_button: Click left or right button
    """
    state = 1
    if not left_button:
        state = 4
    cmd = "mouse_button %s" % state
    qemu_monitor_command(name=name, cmd=cmd, options='--hmp', **dargs)
    # Sleep 1 sec to make sure VM received mouse button event,
    # then release button(state=0)
    time.sleep(1)
    cmd = "mouse_button 0"
    qemu_monitor_command(name=name, cmd=cmd, options='--hmp', **dargs)
    time.sleep(1)


def iothreadadd(name, thread_id, options=None, **dargs):
    """
    Add an IOThread to the guest domain.

    :param name: domain name
    :param thread_id: domain iothread ID
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "iothreadadd %s %s" % (name, thread_id)
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def iothreaddel(name, thread_id, options=None, **dargs):
    """
    Delete an IOThread from the guest domain.

    :param name: domain name
    :param thread_id: domain iothread ID
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "iothreaddel %s %s" % (name, thread_id)
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def iothreadinfo(name, options=None, **dargs):
    """
    View domain IOThreads.

    :param name: domain name
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "iothreadinfo %s" % name
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def iothreadpin(name, thread_id, cpuset, options=None, **dargs):
    """
    Control domain IOThread affinity.

    :param name: domain name
    :param thread_id: domain iothread ID
    :param cpuset: host cpu number(s) to set
    :param options: options may be live, config and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "iothreadpin %s %s %s" % (name, thread_id, cpuset)
    if options:
        cmd += " %s" % options

    return command(cmd, **dargs)


def iothreadset(name, thread_id, values, options="", **dargs):
    """
    Modifies an existing iothread of the domain using the specified iothread_id

    :param name: domain name
    :param thread_id: domain iothread ID
    :param values: the values to be set
    :param options: options may be live and current
    :param dargs: standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "iothreadset %s %s %s %s" % (name, thread_id, values, options)
    return command(cmd, **dargs)


def domrename(domain, new_name, options="", **dargs):
    """
    Rename an inactive domain.

    :param domain:domain name, id or uuid.
    :param new_name:new domain name.
    :param options:extra param.
    :param dargs: standardized virsh function API keywords
    :return: result from command
    """
    cmd = "domrename %s %s %s" % (domain, new_name, options)
    return command(cmd, **dargs)


def nodedev_event(event=None, event_timeout=None, options="", **dargs):
    """
    List event types, or wait for nodedevice events to occur
    :param event: Event type to wait for
    :param event_timeout: Timeout seconds
    :param options: Extra options
    :param dargs: Standardized virsh function API keywords
    :return: CmdResult instance
    """
    cmd = "nodedev-event %s" % options
    if event:
        cmd += " --event %s" % event
    if event_timeout:
        cmd += " --timeout %s" % event_timeout
    return command(cmd, **dargs)


def backup_begin(name, options="", **dargs):
    """
    Begin domain backup

    :param name: name of domain
    :param options: options of backup-begin command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "backup-begin %s %s" % (name, options)
    return command(cmd, **dargs)


def backup_dumpxml(name, **dargs):
    """
    Dump domain backup xml

    :param name: name of domain
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "backup-dumpxml %s" % name
    return command(cmd, **dargs)


def checkpoint_create(name, options="", **dargs):
    """
    Create domain checkpoint (with xml input)

    :param name: name of domain
    :param options: options of checkpoint-create command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-create %s %s" % (name, options)
    return command(cmd, **dargs)


def checkpoint_create_as(name, options="", **dargs):
    """
    Create domain checkpoint (with options)

    :param name: name of domain
    :param options: options of checkpoint-create-as command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-create-as %s %s" % (name, options)
    return command(cmd, **dargs)


def checkpoint_edit(name, checkpoint, **dargs):
    """
    Edit domain checkpoint

    :param name: name of domain
    :param checkpoint: name of checkpoint
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-edit %s %s" % (name, checkpoint)
    return command(cmd, **dargs)


def checkpoint_info(name, checkpoint, **dargs):
    """
    Output basic information about the checkpoint

    :param name: name of domain
    :param checkpoint: name of checkpoint
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-info %s %s" % (name, checkpoint)
    return command(cmd, **dargs)


def checkpoint_list(name, options="", **dargs):
    """
    List domain's checkpoint(s)

    :param name: name of domain
    :param options: options of checkpoint-list command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-list %s %s" % (name, options)
    return command(cmd, **dargs)


def checkpoint_dumpxml(name, checkpoint, options="", **dargs):
    """
    Dump domain checkpoint xml

    :param name: name of domain
    :param checkpoint: name of checkpoint
    :param options: options of checkpoint-dumpxml command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-dumpxml %s %s %s" % (name, checkpoint, options)
    return command(cmd, **dargs)


def checkpoint_parent(name, checkpoint, **dargs):
    """
    Output the name of the parent checkpoint

    :param name: name of domain
    :param checkpoint: name of checkpoint
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-parent %s %s" % (name, checkpoint)
    return command(cmd, **dargs)


def checkpoint_delete(name, checkpoint, options="", **dargs):
    """
    Delete domain checkpoint

    :param name: name of domain
    :param checkpoint: name of checkpoint
    :param options: options of checkpoint-delete command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object
    """
    cmd = "checkpoint-delete %s %s %s" % (name, checkpoint, options)
    return command(cmd, **dargs)


def guestinfo(name, options="", **dargs):
    """
    Query information about the guest (via agent)

    :param name: VM name
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """
    return command("guestinfo %s %s" % (name, options), **dargs)


def get_user_sshkeys(name, user, **dargs):
    """
    list authorized SSH keys for given user (via agent)

    :param name: VM name
    :param user: user to list authorized keys for
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """
    return command("get-user-sshkeys %s %s" % (name, user), **dargs)


def set_user_sshkeys(name, user, options="", **dargs):
    """
    manipulate authorized SSH keys file for given user (via agent)

    :param name: VM name
    :param user: user to set authorized keys for
    :param options: options of set-user-sshkeys command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """
    return command("set-user-sshkeys %s %s %s" % (name, user, options), **dargs)


def domdirtyrate_calc(name, options="", **dargs):
    """
    Calculate vm's dirty page rate

    :param name: VM name
    :param options: options of domdirtyrate_calc command
    :param dargs: standardized virsh function API keywords
    :return: CmdResult object.
    """

    return command("domdirtyrate-calc %s %s" % (name, options), **dargs)
