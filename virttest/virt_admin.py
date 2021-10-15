"""
Utility classes and functions to handle connection to a libvirt host system

The entire contents of callables in this module (minus the names defined in
NOCLOSE below), will become methods of the Virtadmin and VirtadminPersistent classes.
A Closure class is used to wrap the module functions, lambda does not
properly store instance state in this implementation.

Because none of the methods have a 'self' parameter defined, the classes
are defined to be dict-like, and get passed in to the methods as a the
special ``**dargs`` parameter.  All virtadmin module functions _MUST_ include a
special ``**dargs`` (variable keyword arguments) to accept non-default
keyword arguments.

The standard set of keyword arguments to all functions/modules is declared
in the VirtadminBase class.  Only the 'virtadmin_exec' key is guaranteed to always
be present, the remainder may or may not be provided.  Therefor, virtadmin
functions/methods should use the dict.get() method to retrieve with a default
for non-existant keys.

:copyright: 2012 Red Hat Inc.
"""

import signal
import logging
import re
import weakref
import time
import select

import aexpect
from aexpect import remote

from avocado.utils import path
from avocado.utils import process

from virttest import propcan
from virttest import utils_misc
from virttest import utils_split_daemons
from virttest import utils_config


# list of symbol names NOT to wrap as Virtadmin class methods
# Everything else from globals() will become a method of Virtadmin class
NOCLOSE = list(globals().keys()) + [
    'NOCLOSE', 'SCREENSHOT_ERROR_COUNT', 'VIRTADMIN_COMMAND_CACHE',
    'VIRTADMIN_EXEC', 'VirtadminBase', 'VirtadminClosure', 'VirtadminSession', 'Virtadmin',
    'VirtadminPersistent', 'VirtadminConnectBack', 'VIRTADMIN_COMMAND_GROUP_CACHE',
    'VIRTADMIN_COMMAND_GROUP_CACHE_NO_DETAIL',
]

# Needs to be in-scope for Virtadmin* class screenshot method and module function
SCREENSHOT_ERROR_COUNT = 0

# Cache of virtadmin commands, used by help_command_group() and help_command_only()
# TODO: Make the cache into a class attribute on VirtadminBase class.
VIRTADMIN_COMMAND_CACHE = None
VIRTADMIN_COMMAND_GROUP_CACHE = None
VIRTADMIN_COMMAND_GROUP_CACHE_NO_DETAIL = False

# This is used both inside and outside classes
try:
    VIRTADMIN_EXEC = path.find_command("virt-admin")
except path.CmdNotFoundError:
    logging.getLogger('avocado.app').warning(
        "virt-admin executable not set or found on path, virtadmin-admin module"
        " will not function normally")
    VIRTADMIN_EXEC = '/bin/true'

LOG = logging.getLogger('avocado.' + __name__)


class VirtadminBase(propcan.PropCanBase):

    """
    Base Class storing libvirt Connection & state to a host
    """

    __slots__ = ('uri', 'ignore_status', 'debug', 'virtadmin_exec', 'readonly')

    def __init__(self, *args, **dargs):
        """
        Initialize instance with virtadmin_exec always set to something
        """
        init_dict = dict(*args, **dargs)
        init_dict['virtadmin_exec'] = init_dict.get('virtadmin_exec', VIRTADMIN_EXEC)
        init_dict['uri'] = init_dict.get('uri', None)
        init_dict['debug'] = init_dict.get('debug', False)
        init_dict['ignore_status'] = init_dict.get('ignore_status', False)
        init_dict['readonly'] = init_dict.get('readonly', False)
        super(VirtadminBase, self).__init__(init_dict)

    def get_uri(self):
        """
        Accessor method for 'uri' property that must exist
        """
        # self.get() would call get_uri() recursively
        try:
            return self.__dict_get__('uri')
        except KeyError:
            return None


class VirtadminSession(aexpect.ShellSession):

    """
    A virtadmin shell session, used with Virtadmin instances.
    """

    # No way to get virtadmin sub-command "exit" status
    # Check output against list of known error-status strings
    ERROR_REGEX_LIST = ['error:\s*.+$', '.*failed.*']

    def __init__(self, virtadmin_exec=None, uri=None, a_id=None,
                 prompt=r"virt-admin\s*[\#\>]\s*", remote_ip=None,
                 remote_user=None, remote_pwd=None,
                 ssh_remote_auth=False, readonly=False,
                 unprivileged_user=None,
                 auto_close=False, check_libvirtd=True):
        """
        Initialize virtadmin session server, or client if id set.

        :param virtadmin_exec: path to virtadmin executable
        :param uri: uri of libvirt instance to connect to
        :param id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param prompt: Regular expression describing the shell's prompt line.
        :param remote_ip: Hostname/IP of remote system to ssh into (if any)
        :param remote_user: Username to ssh in as (if any)
        :param remote_pwd: Password to use, or None for host/pubkey
        :param auto_close: Param to init ShellSession.
        :param ssh_remote_auth: ssh to remote first.(VirtadminConnectBack).
                                Then execute virtadmin commands.

        Because the VirtadminSession is designed for class VirtadminPersistent, so
        the default value of auto_close is False, and we manage the reference
        to VirtadminSession in VirtadminPersistent manually with counter_increase and
        counter_decrease. If you really want to use it directly over VirtadminPe-
        rsistent, please init it with auto_close=True, then the session will
        be closed in __del__.

            * session = VirtadminSession(virtadmin.VIRSH_EXEC, auto_close=True)
        """

        self.uri = uri
        self.remote_ip = remote_ip
        self.remote_user = remote_user
        self.remote_pwd = remote_pwd

        # Special handling if setting up a remote session
        if ssh_remote_auth:  # remote to remote
            LOG.error("remote session is not supported by virt-admin yet.")
            if remote_pwd:
                pref_auth = "-o PreferredAuthentications=password"
            else:
                pref_auth = "-o PreferredAuthentications=hostbased,publickey"
            # ssh_cmd is not None flags this as remote session
            ssh_cmd = ("ssh -o UserKnownHostsFile=/dev/null %s -p %s %s@%s"
                       % (pref_auth, 22, self.remote_user, self.remote_ip))
            if uri:
                self.virtadmin_exec = ("%s \"%s -c '%s'\""
                                       % (ssh_cmd, virtadmin_exec, self.uri))
            else:
                self.virtadmin_exec = ("%s \"%s\"" % (ssh_cmd, virtadmin_exec))
        else:  # setting up a local session or re-using a session
            self.virtadmin_exec = virtadmin_exec
            if self.uri:
                self.virtadmin_exec += " -c '%s'" % self.uri
            ssh_cmd = None  # flags not-remote session

        if unprivileged_user:
            self.virtadmin_exec = "su - %s -c '%s'" % (unprivileged_user,
                                                       self.virtadmin_exec)

        # aexpect tries to auto close session because no clients connected yet
        aexpect.ShellSession.__init__(self, self.virtadmin_exec, a_id,
                                      prompt=prompt, auto_close=auto_close)

        # Handle remote session prompts:
        # 1.remote to remote with ssh
        # 2.local to remote with "virtadmin -c uri"
        if ssh_remote_auth or self.uri:
            # Handle ssh / password prompts
            remote.handle_prompts(self, self.remote_user, self.remote_pwd,
                                  prompt, debug=True)

        # fail if libvirtd is not running
        if check_libvirtd:
            if self.cmd_status('uri', timeout=60) != 0:
                LOG.debug("Persistent virt-admin session is not responding, "
                          "libvirtd may be dead.")
                self.auto_close = True
                raise aexpect.ShellStatusError(virtadmin_exec, 'uri')

    def cmd_status_output(self, cmd, timeout=60, internal_timeout=None,
                          print_func=None, safe=False):
        """
        Send a virtadmin command and return its exit status and output.

        :param cmd: virtadmin command to send (must not contain newline characters)
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
        """
        Mimic process.run()
        :param cmd: virtadmin command to send.
        :param timeout: Time we'll wait until the process is finished.
        :returns: The command result object.
        """
        exit_status, stdout = self.cmd_status_output(cmd, timeout=timeout)
        stderr = ''  # no way to retrieve this separately
        result = process.CmdResult(cmd, stdout, stderr, exit_status)
        result.stdout = result.stdout_text
        result.stderr = result.stderr_text
        if not ignore_status and exit_status:
            raise process.CmdError(cmd, result,
                                   "Virtadmin Command returned non-zero exit status")
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
                # When use VirtadminPersistent initiate a virtadmin session, an list
                # command is send in to test libvirtd status, and the first
                # command output will be like:
                # Welcome to virtadmin, the virtualization interactive terminal.
                #
                # Type:  'help' for help with commands
                #       'quit' to quit
                #
                # virtadmin #  Id    Name                           State
                #----------------------------------------------------
                #
                # virtadmin #
                # the session help info is included, and the exact output
                # should be the content start after first virtadmin # prompt.
                # The list command did no harm here with help info included,
                # but sometime other commands get list command output included,
                # e.g.
                #  Running virtadmin command: net-list --all
                #  Sending command: net-list --all
                #  Id    Name                           State
                #  ----------------------------------------------------
                #
                # virtadmin #  Name            State      Autostart     Persistent
                #  ----------------------------------------------------------
                #  default              active     yes           yes
                #
                # virtadmin #
                # The list command output is mixed in the net-list command
                # output, this will fail to extract network name if use set
                # number 2 in list of output splitlines like in function
                # virtadmin.net_state_dict.
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
class VirtadminClosure(object):

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


class Virtadmin(VirtadminBase):

    """
    Execute libvirt operations, using a new virtadmin shell each time.
    """

    __slots__ = []

    def __init__(self, *args, **dargs):
        """
        Initialize Virtadmin instance with persistent options

        :param args: Initial property keys/values
        :param dargs: Initial property keys/values
        """
        super(Virtadmin, self).__init__(*args, **dargs)
        # Define the instance callables from the contents of this module
        # to avoid using class methods and hand-written aliases
        for sym, ref in list(globals().items()):
            if sym not in NOCLOSE and callable(ref):
                # Adding methods, not properties, so avoid special __slots__
                # handling.  __getattribute__ will still find these.
                self.__super_set__(sym, VirtadminClosure(ref, self))


class VirtadminPersistent(Virtadmin):

    """
    Execute libvirt operations using persistent virtadmin session.
    """

    __slots__ = ('session_id', 'remote_pwd', 'remote_user', 'uri',
                 'remote_ip', 'ssh_remote_auth', 'unprivileged_user',
                 'readonly')

    # B/c the auto_close of VirtadminSession is False, we
    # need to manage the ref-count of it manually.
    COUNTERS = {}

    def __init__(self, *args, **dargs):
        super(VirtadminPersistent, self).__init__(*args, **dargs)
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
            VirtadminPersistent.COUNTERS[session_id] = 1
            return
        # increase the counter of session_id.
        VirtadminPersistent.COUNTERS[session_id] += 1

    def counter_decrease(self):
        """
        Method to decrease the counter to self.a_id in COUNTERS.
        If the counter is less than 1, it means there is no more
        VirtadminSession instance referring to the session. So close
        this session, and return True.
        Else, decrease the counter in COUNTERS and return False.
        """
        session_id = self.__dict_get__("session_id")
        self.__class__.COUNTERS[session_id] -= 1
        counter = self.__class__.COUNTERS[session_id]
        if counter <= 0:
            # The last reference to this session. Closing it.
            session = VirtadminSession(a_id=session_id)
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
                    existing = VirtadminSession(a_id=session_id)
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
        virtadmin_exec = self.__dict_get__('virtadmin_exec')
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
        new_session = VirtadminSession(virtadmin_exec, uri, a_id=None,
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


class VirtadminConnectBack(VirtadminPersistent):

    """
    Persistent virtadmin session connected back from a remote host
    """

    __slots__ = ('remote_ip', )

    def new_session(self):
        """
        Open new remote session, closing any existing
        """

        # Accessors may call this method, avoid recursion
        # Must exist, can't be None
        virtadmin_exec = self.__dict_get__('virtadmin_exec')
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
        super(VirtadminConnectBack, self).close_session()
        new_session = VirtadminSession(virtadmin_exec, uri, a_id=None,
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


# virtadmin module functions follow (See module docstring for API) #####


def command(cmd, **dargs):
    """
    Interface to cmd function as 'cmd' symbol is polluted.

    :param cmd: Command line to append to virtadmin command
    :param dargs: standardized virtadmin function API keywords
    :return: CmdResult object
    :raise: CmdError if non-zero exit status and ignore_status=False
    """

    virtadmin_exec = dargs.get('virtadmin_exec', VIRTADMIN_EXEC)
    uri = dargs.get('uri', None)
    debug = dargs.get('debug', False)
    # Caller deals with errors
    ignore_status = dargs.get('ignore_status', True)
    session_id = dargs.get('session_id', None)
    readonly = dargs.get('readonly', False)
    unprivileged_user = dargs.get('unprivileged_user', None)
    timeout = dargs.get('timeout', None)

    # Check if this is a VirtadminPersistent method call
    if session_id:
        # Retrieve existing session
        session = VirtadminSession(a_id=session_id)
    else:
        session = None

    if debug:
        LOG.debug("Running virtadmin command: %s", cmd)

    if timeout:
        try:
            timeout = int(timeout)
        except ValueError:
            LOG.error("Ignore the invalid timeout value: %s", timeout)
            timeout = None

    if session:
        # Utilize persistent virtadmin session, not suit for readonly mode
        if readonly:
            LOG.debug("Ignore readonly flag for this virtadmin session")
        if timeout is None:
            timeout = 60
        ret = session.cmd_result(cmd, ignore_status=ignore_status,
                                 debug=debug, timeout=timeout)
        # Mark return value with session it came from
        ret.from_session_id = session_id
    else:
        # Normal call to run virtadmin command
        # Readonly mode
        if readonly:
            LOG.error("readonly mode is not supported by virt-admin yet.")
#            cmd = " -r " + cmd

        if uri:
            # uri argument IS being used
            uri_arg = " -c '%s' " % uri
        else:
            uri_arg = " "  # No uri argument being used

        cmd = "%s%s%s" % (virtadmin_exec, uri_arg, cmd)

        if unprivileged_user:
            # Run cmd as unprivileged user
            cmd = "su - %s -c '%s'" % (unprivileged_user, cmd)

        # Raise exception if ignore_status is False
        ret = process.run(cmd, timeout=timeout, verbose=debug,
                          ignore_status=ignore_status,
                          shell=True)
        # Mark return as not coming from persistent virtadmin session
        ret.from_session_id = None

    # Always log debug info, if persistent session or not
    if debug:
        LOG.debug("status: %s", ret.exit_status)
        LOG.debug("stdout: %s", ret.stdout_text.strip())
        LOG.debug("stderr: %s", ret.stderr_text.strip())

    # Return CmdResult instance when ignore_status is True
    return ret


def check_server_name(server_name="virtproxyd"):
    """
    Determine the server name under different daemon mode.

    :param server_name: name of the managed server
    :return: name of the managed server
    """
    if not utils_split_daemons.is_modular_daemon():
        server_name = "libvirtd"
    return server_name


def managed_daemon_config(conf_type="virtproxyd"):
    """
    Determine different daemon config under different daemon mode.

    :param conf_type: The configuration type to get
        For example, "libvirtd" or "virtqemud"
    :return: utils_config.LibvirtConfigCommon object
    """
    if not utils_split_daemons.is_modular_daemon():
        conf_type = "libvirtd"
    config = utils_config.get_conf_obj(conf_type)
    return config


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


def srv_list(**dargs):
    """
    Run srv_list command in virt_admin session.

    :param dargs: standardized virt-admin function API keywords
    :return: CmdResult object
    """
    cmd = "srv-list"
    return command(cmd, **dargs)


def srv_threadpool_info(server_name, **dargs):
    """
    Run srv-threadpool-info in virt-admin session.
    :param server_name: list the attributes of the server with this name.
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "srv-threadpool-info %s" % server_name
    return command(cmd, **dargs)


def srv_clients_info(server_name, **dargs):
    """
    Run srv-clients-info in virt-admin session
    :param server_name: list the attributes of the server with this name.
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "srv-clients-info %s " % server_name
    return command(cmd, **dargs)


def server_update_tls(server_name, **dargs):
    """
    Run server-update-tls in virt-admin session
    :param server_name: name of the server
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "server-update-tls %s " % server_name
    return command(cmd, **dargs)


def srv_clients_list(server_name, **dargs):
    """
    Run srv-clients-list in virt-admin session
    :param server_name: list clients connected to this server.
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "srv-clients-list %s " % server_name
    return command(cmd, **dargs)


def client_info(server_name, client_id, **dargs):
    """
    Run client-info in virt-admin session
    :param server_name: list clients connected to this server.
    :param client_id: client id number.
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "client-info %s %s " % (server_name, client_id)
    return command(cmd, **dargs)


def srv_threadpool_set(server_name, min_workers=None,
                       max_workers=None, prio_workers=None,
                       options=None, **dargs):
    """
    Run srv-threadpool-set in virt-admin session
    :param server_name: set the workpool parameters of this server.
    :param min_workers: set the bottom limit to the number of workers.
    :param max_workers: set the upper limit to the number of workers.
    :param prio_workers: change the current number of priority workers.
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "srv-threadpool-set %s" % server_name
    if min_workers:
        cmd += " --min-workers %s" % min_workers
    if max_workers:
        cmd += " --max-workers %s" % max_workers
    if prio_workers:
        cmd += " --priority-workers %s" % prio_workers
    if options:
        cmd += " %s" % options
    return command(cmd, **dargs)


def srv_clients_set(server_name, max_unauth_clients=None,
                    max_clients=None, options=None, **dargs):
    """
    Run srv-clients-set: set server's client-related configuration limits.
    :param max_unauth_clients: set the upper limit to number of clients
    for authentication to be connected to the server
    :param max_clients: set the upper limit to overall number of clients
    connected to the server.
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "srv-clients-set %s" % server_name
    if max_unauth_clients:
        cmd += " --max-unauth-clients %s" % max_unauth_clients
    if max_clients:
        cmd += " --max-clients %s" % max_clients
    if options:
        cmd += " %s" % options
    return command(cmd, **dargs)


def client_disconnect(server_name, client_id, **dargs):
    """
    Run client-disconnect: force disconnect a client from the given server
    :param server_name: the name of the server the client is currently connected to
    :param client_id: close a connection originating from client client_id
    :param dargs: standardized virt-admin function API keywords.
    :return: CmdResult object
    """
    cmd = "client-disconnect %s %s" % (server_name, client_id)
    return command(cmd, **dargs)
