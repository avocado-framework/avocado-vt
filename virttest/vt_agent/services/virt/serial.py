import logging
import re

from managers import console_mgr, vmm
from virttest import utils_misc

from aexpect import remote
from aexpect.exceptions import (
    ExpectError,
    ExpectProcessTerminatedError,
    ExpectTimeoutError,
)

VMM = vmm.VirtualMachinesManager()
LOG = logging.getLogger("avocado.service." + __name__)


def open_serial(
    instance_id, name, linesep="\n", prompt=r"[\#\$]\s*$", status_test_command="echo $?"
):
    params = {
        "linesep": linesep,
        "prompt": prompt,
        "status_test_command": status_test_command,
    }
    instance_info = VMM.get_instance(instance_id)
    instance_driver = instance_info["driver"]
    serials = instance_driver.get_serials()
    file_name = serials.get(name).get("filename")
    console = console_mgr.create_console(name, instance_id, "serial", file_name, params)
    serial_id = utils_misc.generate_random_string(16)
    console_mgr.register_console(serial_id, console)
    return serial_id


def login_serial(serial_id, username, password, prompt, timeout=10):
    serial = console_mgr.get_console(serial_id)
    prompt = re.compile(prompt)
    try:
        output = remote.handle_prompts(serial, username, password, prompt, timeout)
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return output
    except Exception as e:
        if isinstance(e, remote.LoginTimeoutError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginTimeoutError(output)
        elif isinstance(e, remote.LoginProcessTerminatedError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginProcessTerminatedError(e.status, output)
        elif isinstance(e, remote.LoginAuthenticationError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginProcessTerminatedError(output)
        elif isinstance(e, remote.LoginError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginError(e.msg, output)
        raise e


def close_serial(serial_id):
    serial = console_mgr.get_console(serial_id)
    return serial.close()


def is_alive_serial(serial_id):
    serial = console_mgr.get_console(serial_id)
    return serial.is_alive()


def cmd(serial_id, cmd, timeout=60, ok_status=None, ignore_all_errors=False):
    serial = console_mgr.get_console(serial_id)
    return serial.cmd(
        cmd=cmd,
        timeout=timeout,
        ok_status=ok_status,
        ignore_all_errors=ignore_all_errors,
    )


def cmd_output(serial_id, cmd, timeout=60, safe=False):
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_output(cmd=cmd, timeout=timeout, safe=safe)


def cmd_output_safe(serial_id, cmd, timeout=60):
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_output_safe(cmd=cmd, timeout=timeout)


def cmd_status(serial_id, cmd, timeout=60, safe=False):
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_status(cmd=cmd, timeout=timeout, safe=safe)


def cmd_status_output(serial_id, cmd, timeout=60, safe=False):
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_status_output(cmd=cmd, timeout=timeout, safe=safe)


def is_responsive(serial_id):
    serial = console_mgr.get_console(serial_id)
    return serial.is_responsive()


def send(serial_id, cont=""):
    serial = console_mgr.get_console(serial_id)
    serial.send(cont)


def sendline(serial_id, cont=""):
    serial = console_mgr.get_console(serial_id)
    serial.sendline(cont)


def sendcontrol(serial_id, char):
    serial = console_mgr.get_console(serial_id)
    return serial.sendcontrol(char)


def send_ctrl(serial_id, control_str=""):
    serial = console_mgr.get_console(serial_id)
    serial.send_ctrl(control_str)


def set_linesep(serial_id, linesep):
    serial = console_mgr.get_console(serial_id)
    return serial.set_linesep(linesep)


def set_status_test_command(serial_id, command):
    serial = console_mgr.get_console(serial_id)
    return serial.set_status_test_command(command)


def read_nonblocking(serial_id, timeout=60, internal_timeout=None):
    serial = console_mgr.get_console(serial_id)
    data = serial.read_nonblocking(timeout=timeout, internal_timeout=internal_timeout)
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")
    return data


def read_until_output_matches(serial_id, patterns, timeout=60, internal_timeout=None):
    serial = console_mgr.get_console(serial_id)
    _patterns = []
    for pattern in patterns:
        _patterns.append(re.compile(pattern))
    return serial.read_until_output_matches(
        _patterns, timeout=timeout, internal_timeout=internal_timeout
    )


def read_until_last_line_matches(
    serial_id, patterns, timeout=60, internal_timeout=None
):
    serial = console_mgr.get_console(serial_id)
    _patterns = []
    for pattern in patterns:
        _patterns.append(re.compile(pattern))

    try:
        match, output = serial.read_until_last_line_matches(
            _patterns, timeout=timeout, internal_timeout=internal_timeout
        )
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return match, output

    except ExpectTimeoutError as e:
        output = e.output
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return -1, output

    except ExpectProcessTerminatedError as e:
        output = e.output
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return -2, output

    except ExpectError as e:
        output = e.output
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return -3, output


def read_until_any_line_matches(serial_id, patterns, timeout=60, internal_timeout=None):
    serial = console_mgr.get_console(serial_id)
    _patterns = []
    for pattern in patterns:
        _patterns.append(re.compile(pattern))
    return serial.read_until_any_line_matches(
        patterns, timeout=timeout, internal_timeout=internal_timeout
    )


def read_up_to_prompt(serial_id, timeout=60, internal_timeout=None):
    serial = console_mgr.get_console(serial_id)
    return serial.read_up_to_prompt(timeout=timeout, internal_timeout=internal_timeout)


def get_output(serial_id):
    serial = console_mgr.get_console(serial_id)
    output = serial.get_output()
    if isinstance(output, str):
        output = output.encode("utf-8", "ignore")
    return output
