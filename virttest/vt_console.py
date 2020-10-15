import threading


from aexpect import remote


class ConsoleError(Exception):
    """A base class for console errors."""
    pass


class NoConsoleError(ConsoleError):
    """Raise when there is no console available for a session."""

    pass


class ConsoleBusyError(ConsoleError):
    """Raise when session tries to communicate with a console in use."""

    pass


def lock(function):
    """
    Get the ConsoleManager lock, run the function, then release the lock.

    :param function: Function to wrap.
    """
    def wrapper(*args, **kwargs):
        console_manager = args[0]
        if not console_manager._lock.acquire(False):
            raise ConsoleBusyError("Console is in use.")
        try:
            return function(*args, **kwargs)
        finally:
            console_manager._lock.release()
    return wrapper


class ConsoleManager(object):
    """A class for console session communication pipeline."""

    def __init__(self):
        self._console = None
        self.status_test_command = None
        self._lock = threading.Lock()

    def __getstate__(self):
        state = self.__dict__.copy()
        del state["_lock"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock = threading.Lock()

    @lock
    def __login(self, linesep, status_test_command,
                prompt, username, password, timeout):
        self._console.set_linesep(linesep)
        self._console.set_status_test_command(status_test_command)
        remote.handle_prompts(self._console, username, password,
                              prompt, timeout)

    def create_session(self, linesep, status_test_command,
                       prompt, username, password, timeout):
        """
        Return a console session with itself as the manager.

        :param linesep: line separator for console
        :param status_test_command: status test command for console
        :param prompt: console prompt pattern
        :param username: login username
        :param password: login password
        :param timeout: time (seconds) before giving up logging into the guest
        """
        if self._console is None:
            raise NoConsoleError("No console available.")
        self.__login(linesep, status_test_command, prompt,
                     username, password, timeout)
        return ConsoleSession(self)

    def set_console(self, console):
        self._console = console
        if self._console is not None:
            self.status_test_command = self._console.status_test_command

    @lock
    def proxy_call(self, func, *args, **kwargs):
        """Proxy function call to call functions provided by a Console."""

        _func = getattr(self._console, func)
        return _func(*args, **kwargs)


class ConsoleSession(object):
    """
    A wrapper for communicating with console.

    For more detailed function call information,
    you may need to refer to aexpect.client.ShellSession().
    """

    def __init__(self, manager):
        self.__manager = manager
        self.status_test_command = manager.status_test_command
        self.__closed = False

    def __repr__(self):
        return "<console session %s>" % id(self)

    def __verify_session_status(self):
        """Check the session status,if it is closed, raise error."""
        if self.__closed:
            raise RuntimeError("%s is closed." % self)

    def is_responsive(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.is_responsive.__name__,
                                         *args, **kwargs)

    def cmd_output(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.cmd_output.__name__,
                                         *args, **kwargs)

    def cmd_output_safe(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.cmd_output_safe.__name__,
                                         *args, **kwargs)

    def cmd_status_output(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.cmd_status_output.__name__,
                                         *args, **kwargs)

    def cmd_status(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.cmd_status.__name__,
                                         *args, **kwargs)

    def cmd(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.cmd.__name__,
                                         *args, **kwargs)

    def close(self):
        self.__verify_session_status()
        self.__closed = True

# FIXME: the following methods are temporarily introduced to workaround
#        console-session issues caused by the incorrect usages

    def send(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.send.__name__,
                                         *args, **kwargs)

    def sendline(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.sendline.__name__,
                                         *args, **kwargs)

    def sendcontrol(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.sendcontrol.__name__,
                                         *args, **kwargs)

    def send_ctrl(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.send_ctrl.__name__,
                                         *args, **kwargs)

    def set_linesep(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.set_linesep.__name__,
                                         *args, **kwargs)

    def read_nonblocking(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.read_nonblocking.__name__,
                                         *args, **kwargs)

    def read_until_output_matches(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(
            self.read_until_output_matches.__name__, *args, **kwargs)

    def read_until_last_line_matches(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(
            self.read_until_last_line_matches.__name__, *args, **kwargs)

    def read_until_any_line_matches(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(
            self.read_until_any_line_matches.__name__, *args, **kwargs)

    def read_up_to_prompt(self, *args, **kwargs):
        self.__verify_session_status()
        return self.__manager.proxy_call(self.read_up_to_prompt.__name__,
                                         *args, **kwargs)
