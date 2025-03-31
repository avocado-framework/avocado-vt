from .protocol import RunState


class ConnectError(Exception):
    pass


class ConnectLockError(ConnectError):
    pass


class SocketConnectError(ConnectError):
    def __init__(self, msg, err):
        Exception.__init__(self, msg, err)
        self._msg = msg
        self._err = err

    def __str__(self):
        return f"{self._msg}    {self._err}"


class ProtocolError(Exception):
    """
    Abstract error class for protocol failures.

    Semantically, these errors are generally the fault of either the
    protocol server or as a result of a bug in this library.

    :param error_message: Human-readable string describing the error.
    """
    def __init__(self, error_message: str, *args: object):
        super().__init__(error_message, *args)
        #: Human-readable error message, without any prefix.
        self.error_message: str = error_message

    def __str__(self) -> str:
        return self.error_message


class ProtocolStateError(ProtocolError):
    def __init__(self, except_state: RunState, state):
        error_message = (
            f"Expected state {except_state} but got {state}")
        super(ProtocolStateError, self).__init__(error_message)
