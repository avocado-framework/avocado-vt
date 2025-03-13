import logging

from ..protocol import SocketProtocol
from ..message import Message

from virttest import utils_misc

from typing import (
    Dict,
    Iterator,
    Mapping,
    MutableMapping,
    Optional,
    Union,
    List,
)

LOG = logging.getLogger("avocado." + __name__)


class QMPError(Exception):
    """Abstract error class for all errors originating from this package."""


class ExecuteError(QMPError):
    """
    Exception raised by `QMPClient.execute()` on RPC failure.

    This exception is raised when the server received, interpreted, and
    replied to a command successfully; but the command itself returned a
    failure status.

    For example::

        await qmp.execute('block-dirty-bitmap-add',
                          {'node': 'foo', 'name': 'my_bitmap'})
        # qemu.qmp.qmp_client.ExecuteError:
        #     Cannot find device='foo' nor node-name='foo'

    :param error_response: The RPC error response object.
    :param sent: The sent RPC message that caused the failure.
    :param received: The raw RPC error reply received.
    """
    def __init__(self, error_response: ErrorResponse,
                 sent: Message, received: Message):
        super().__init__(error_response, sent, received)
        #: The sent `Message` that caused the failure
        self.sent: Message = sent
        #: The received `Message` that indicated failure
        self.received: Message = received
        #: The parsed error response
        self.error: ErrorResponse = error_response

    @property
    def error_class(self) -> str:
        """The QMP error class"""
        return self.error.error.class_

    def __str__(self) -> str:
        return self.error.error.desc


class QMPClient(SocketProtocol):
    def __init__(self, name):
        super().__init__(name, "tcp")

    def _initial_capabilities(self):
        LOG.info("Initializing capabilities ...")
        arguments: Dict[str, List[str]] = {}
        self.execute("qmp_capabilities", arguments)

    def _do_establish_session(self):
        self._initial_capabilities()

    @staticmethod
    def make_execute_msg(cmd: str,
                         arguments: Union[bytes, Mapping[str, object]] = None) -> Message:
        msg = Message({'execute': cmd})
        if arguments is not None:
            msg['arguments'] = arguments

        return msg

    @staticmethod
    def _get_exec_id() -> str:
        return utils_misc.generate_random_string(8)

    def _send_msg(self, msg: Message) -> str:
        super().send(data=msg)
        return msg["id"]

    def _recv(self, exec_id: str) -> object:
        return

    def _execute(self, msg: Message, assign_id: bool = True) -> Message:
        if assign_id:
            msg['id'] = self._get_exec_id()

        elif 'id' in msg:
            assert isinstance(msg['id'], str)

        exec_id = self._send_msg(msg)
        return self._recv(exec_id)

    def execute_msg(self, msg: Message) -> object:
        if not ('execute' in msg or 'exec-oob' in msg):
            raise ValueError("Requires 'execute' or 'exec-oob' message")

        # Copy the Message so that the ID assigned by _execute() is
        # local to this method; allowing the ID to be seen in raised
        # Exceptions but without modifying the caller's held copy.
        msg = Message(msg)
        reply = self._execute(msg)

        if 'error' in reply:
            try:
                error_response = ErrorResponse(reply)
            except (KeyError, TypeError) as err:
                # Error response was malformed.
                raise BadReplyError(
                    "QMP error reply is malformed", reply, msg,
                ) from err

            raise ExecuteError(error_response, msg, reply)

        if 'return' not in reply:
            raise BadReplyError(
                "QMP reply is missing a 'error' or 'return' member",
                reply, msg,
            )

        return reply['return']

    def execute(self, cmd: str,
                arguments: Union[bytes, Mapping[str, object]] = None) -> object:
        LOG.info(f"Executing QMP command {cmd} with arguments {arguments}")
        msg = self.make_execute_msg(cmd, arguments)
        return self.execute_msg(msg)
