import logging
import socket
import array
import threading
import time
import select

from enum import Enum


from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
    cast,
)


from .error import SocketConnectError, ConnectLockError, ProtocolStateError

LOG = logging.getLogger("avocado." + __name__)


class RunState(Enum):
    """Protocol session run state."""

    #: Fully quiesced and disconnected.
    IDLE = 0
    #: In the process of connecting or establishing a session.
    CONNECTING = 1
    #: Fully connected and active session.
    RUNNING = 2
    #: In the process of disconnecting.
    #: RunState may be returned to `IDLE` by calling `disconnect()`.
    DISCONNECTING = 3


class Protocol(object):
    def __init__(self):
        pass

    def create_connect(self):
        pass

    def send(self):
        pass

    def recv(self):
        return

    def close_connect(self):
        pass

    def __del__(self):
        pass


class SocketProtocol(object):

    ACQUIRE_LOCK_TIMEOUT = 20
    DATA_AVAILABLE_TIMEOUT = 0
    CONNECT_TIMEOUT = 60

    def __init__(self, socket_type: str, name: Optional[str] = None) -> None:
        self._name = name
        self._lock = threading.RLock()
        self._server_closed = False
        self._socket_type = socket_type
        self._runstate = RunState.IDLE
        if socket_type == "tcp":
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif socket_type == "unix":
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            raise NotImplementedError(
                f"Socket type f{self._socket_type} not supported")

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        tokens = []
        if self.name is not None:
            tokens.append(f"name={self._name!r}")
        tokens.append(f"runstate={self._runstate.name}")
        return f"<{cls_name} {' '.join(tokens)}>"

    @property
    def name(self) -> Optional[str]:
        """
        The nickname for this connection, if any.

        This name is used for differentiating instances in debug output.
        """
        return self._name

    @property
    def runstate(self) -> RunState:
        return self._runstate

    def _set_state(self, state: RunState) -> None:
        """
        Change the `Runstate` of the protocol connection.

        Signals the `runstate_changed` event.
        """
        if state == self._runstate:
            return

        LOG.debug("Transitioning from '%s' to '%s'.",
                  str(self._runstate), str(state))
        self._runstate = state
        # self._runstate_event.set()
        # self._runstate_event.clear()

    def _acquire_lock(self, timeout=ACQUIRE_LOCK_TIMEOUT, lock=None):
        end_time = time.time() + timeout
        if not lock:
            lock = self._lock
        while time.time() < end_time:
            if lock.acquire(False):
                return True
            time.sleep(0.05)
        return False

    def _release_lock(self, lock=None):
        if not lock:
            lock = self._lock
        lock.release()

    def _do_connect(self, address, timeout):
        if self._runstate != RunState.IDLE:
            raise ProtocolStateError(RunState.IDLE, self._runstate)
        try:
            self._set_state(RunState.CONNECTING)
            self._socket.settimeout(timeout)
            if self._socket_type == "tcp":
                self._socket.connect(*address)
            elif self._socket_type == "unix":
                self._socket.connect(address)

        except socket.error as e:
            raise SocketConnectError(f"Could not connect to socket", e)

    def _do_establish_session(self):
        raise NotImplementedError

    def _establish_session(self):
        if self._runstate != RunState.CONNECTING:
            raise ProtocolStateError(RunState.CONNECTING, self._runstate)

        self._do_establish_session()
        self._set_state(RunState.RUNNING)

    def connect(self, address, timeout=CONNECT_TIMEOUT):
        self._do_connect(address, timeout)
        self._establish_session()

    def disconnect(self):
        try:
            self._set_state(RunState.DISCONNECTING)
            self._socket.shutdown(socket.SHUT_RDWR)
        except socket.error as e:
            LOG.warning(e)
            pass
        self._socket.close()
        self._set_state(RunState.IDLE)

    def send(self, data, fds=None):
        func = self._socket.sendall
        args = [data + b"\n"]
        if fds:
            func = self._socket.sendmsg
            args = [
                args,
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))],
            ]
        if not self._acquire_lock():
            raise ConnectLockError(
                f"Could not acquire exclusive lock to send data: {data}")
        try:
            try:
                func(*args)
            except socket.error as e:
                raise SocketConnectError(f"Could not send data: {data}", e)
        finally:
            self._release_lock()

    def _data_available(self, timeout=DATA_AVAILABLE_TIMEOUT):
        if self._server_closed:
            return False
        timeout = max(0, timeout)
        try:
            return bool(select.select([self._socket], [], [], timeout)[0])
        except socket.error as e:
            raise SocketConnectError("Verifying data on socket", e)

    def recv(self):
        s = b""
        while self._data_available():
            try:
                data = self._socket.recv(1024)
            except socket.error as e:
                raise SocketConnectError("Could not receive data from socket", e)
            if not data:
                self._server_closed = True
                break
            s += data
        return s

    def __del__(self):
        self.disconnect()
