import logging
import os

import aexpect
from vt_agent.core.data_dir import LOG_DIR

from virttest import utils_logfile, utils_misc

LOG = logging.getLogger("avocado.service." + __name__)


class Console(object):
    def __init__(self, instance_id, console_type, console=None):
        self._instance_id = instance_id
        self._console_type = console_type
        self._console = console

    @property
    def instance_id(self):
        return self._instance_id


class SerialConsole(Console):
    def __init__(self, instance_id, console=None):
        super(SerialConsole, self).__init__(instance_id, "serial", console)

    def __getattr__(self, item):
        if self._console:
            return getattr(self._console, item)


class ConsoleManager(object):
    """
    Manager the connection to the console for the VM
    """

    def __init__(self):
        self._consoles = {}

    @staticmethod
    def create_console(name, instance_id, console_type, file_name, params={}):
        if console_type == "serial":
            log_name = os.path.join(LOG_DIR, f"{console_type}-{name}-{instance_id}.log")
            serial_session = aexpect.ShellSession(
                "nc -U %s" % file_name,
                auto_close=False,
                output_func=utils_logfile.log_line,
                output_params=(log_name,),
                prompt=params.get("shell_prompt", "[\#\$]"),
                status_test_command=params.get("status_test_command", "echo $?"),
                encoding="UTF-8",
            )
            return SerialConsole(instance_id, console=serial_session)
        elif console_type == "vnc":
            raise NotImplementedError()
        elif console_type == "spice":
            raise NotImplementedError()
        else:
            raise NotImplementedError("Not support console type %s" % console_type)

    def register_console(self, con_id, console):
        if con_id in self._consoles:
            raise ValueError
        self._consoles[con_id] = console

    def unregister_console(self, con_id):
        del self._consoles[con_id]

    def get_console(self, con_id):
        return self._consoles.get(con_id)

    def get_consoles_by_instance(self, instance_id):
        consoles = []
        for console in self._consoles.values():
            if console.instance_id == instance_id:
                consoles.append(console)

        return consoles
