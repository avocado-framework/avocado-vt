"""logging related classes and functions."""
import logging
import re

from virttest import virt_vm


class QemuProcessTermHandler(logging.Handler):
    """
    This handler sends exception to a queue if qemu process exited with
    none-zero status.
    https://github.com/python/cpython/blob/master/Lib/logging/handlers.py
    """

    def __init__(self, queue):
        """
        Initialize an instance, using the passed queue.

        :param queue: passed event queue.
        :type queue: an instance of queue.Queue.
        """
        logging.Handler.__init__(self)
        self.queue = queue

    def enqueue(self, event):
        """Enqueue an event, non-blocking."""
        self.queue.put_nowait(event)

    def emit(self, record):
        """
        Emit a record.

        Writes (VMExitStatusError, VMExitStatusError(vm, status), None) to
        queue if qemu process is exited with non-zero status.
        """
        message = self.format(record)
        pattern = (r"\[(?P<vm>[a-zA-Z0-9-_]+) qemu process output\]"
                   r" \(Process terminated with status (?P<exit_status>\d+)\)")
        match = re.search(pattern, message)
        if match:
            vm, exit_status = match.group("vm", "exit_status")
            if int(exit_status) != 0:
                try:
                    self.enqueue(
                        (virt_vm.VMExitStatusError,
                         virt_vm.VMExitStatusError(vm, exit_status, message),
                         None)
                        )
                except Exception:
                    self.handleError(record)
