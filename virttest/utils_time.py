import logging
import re

from avocado.utils import path
from avocado.utils import process
from avocado.core import exceptions

from virttest import error_context
from virttest import utils_test

# command `grep --color` may have alias name `grep` in some systems,
# so get explicit command 'grep' with path
grep_binary = path.find_command("grep")

LOG = logging.getLogger('avocado.' + __name__)


@error_context.context_aware
def get_host_timezone():
    """
    Get host's timezone
    """
    timezone_cmd = 'timedatectl | %s "Time zone"' % grep_binary
    timezone_pattern = '^(?:\s+Time zone:\s)(\w+\/\S+|UTC)(?:\s\(\S+,\s)([+|-]\d{4})\)$'
    error_context.context("Get host's timezone", LOG.info)
    host_timezone = process.run(timezone_cmd, timeout=240, shell=True).stdout_text
    try:
        host_timezone_set = re.match(timezone_pattern, host_timezone).groups()
        return {"timezone_city": host_timezone_set[0],
                "timezone_code": host_timezone_set[1]}
    except (AttributeError, IndexError):
        raise exceptions.TestError("Fail to get host's timezone.")


@error_context.context_aware
def verify_timezone_linux(session):
    """
    Verify linux guest's timezone

    :param session: VM session
    """
    error_context.context("Verify guest's timezone", LOG.info)
    timezone_cmd = 'timedatectl | %s "Time zone"' % grep_binary
    timezone_pattern = '(?:\s+Time zone:\s)(\w+\/\S+|UTC)(?:\s\(\S+,\s)([+|-]\d{4})\)'
    guest_timezone = session.cmd_output_safe(timezone_cmd, timeout=240)
    try:
        guest_timezone_set = re.search(timezone_pattern, guest_timezone).groups()
        return guest_timezone_set[0] == get_host_timezone()['timezone_city']
    except (AttributeError, IndexError):
        raise exceptions.TestError("Fail to get guest's timezone.")


@error_context.context_aware
def sync_timezone_linux(vm, login_timeout=360):
    """
    Sync linux guest's timezone

    :param vm: Virtual machine object
    :param login_timeout: Time (seconds) to keep trying to log in.
    """
    session = vm.wait_for_login(timeout=login_timeout, serial=True)
    error_context.context("Sync guest's timezone", LOG.info)
    set_timezone_cmd = "timedatectl set-timezone %s"
    if not verify_timezone_linux(session):
        host_timezone_city = get_host_timezone()['timezone_city']
        session.cmd(set_timezone_cmd % host_timezone_city)
        if not verify_timezone_linux(session):
            session.close()
            raise exceptions.TestError("Fail to sync guest's timezone.")
    session.close()


@error_context.context_aware
def verify_timezone_win(session):
    """
    Verify windows guest's timezone

    :params session: VM session
    :return tuple(verify_status, get_timezone_name)
    """
    def get_timezone_list():
        timezone_list_cmd = "tzutil /l"
        timezone_list = session.cmd_output_safe(timezone_list_cmd)

        match_pattern = "(?:\(UTC([+|-]\d{2}:\d{2})?)(?:.*\n)(\w+.*(?:\s\w+)*)"
        timezone_sets = []
        for para in re.split("(?:\r?\n){2,}", timezone_list.strip()):
            result = re.match(match_pattern, para, re.M)
            if not result:
                continue
            code, name = result.groups()
            # When UTC standard time, add timezone code '+0000'
            if not code:
                code = "+0000"
            else:
                code = re.sub(r'(\d{2}):(\d{2})', r'\1\2', code)
            timezone_sets.append((code, name))
        return timezone_sets

    def get_timezone_code(timezone_name):
        for value in get_timezone_list():
            if value[1] == timezone_name:
                return value[0]
        return None

    def get_timezone_name(timezone_code):
        for value in get_timezone_list():
            if value[0] == timezone_code:
                return value[1]
        return None

    error_context.context("Verify guest's timezone", LOG.info)
    timezone_cmd = 'tzutil /g'
    host_timezone_code = get_host_timezone()['timezone_code']
    # Workaround to handle two line prompts in serial session
    timezone_name = session.cmd_output_safe(timezone_cmd).split('\n')[0]
    if get_timezone_code(timezone_name) != host_timezone_code:
        return False, get_timezone_name(host_timezone_code)
    return True, ""


@error_context.context_aware
def sync_timezone_win(vm, login_timeout=360):
    """
    Verify and sync windows guest's timezone

    :param vm: Virtual machine object
    :param login_timeout: Time (seconds) to keep trying to log in
    """
    session = vm.wait_for_login(timeout=login_timeout, serial=True)
    set_timezone_cmd = 'tzutil /s "%s"'
    (ver_result, output) = verify_timezone_win(session)

    if ver_result is not True:
        error_context.context("Sync guest's timezone.", LOG.info)
        session.cmd(set_timezone_cmd % output)
        vm_params = vm.params
        error_context.context("Shutdown guest...", LOG.info)
        vm.destroy()
        error_context.context("Boot guest...", LOG.info)
        vm.create(params=vm_params)
        vm.verify_alive()
        session = vm.wait_for_login(serial=True)
        (ver_result, output) = verify_timezone_win(session)
        if ver_result is not True:
            session.close()
            raise exceptions.TestError("Fail to sync guest's timezone.")
    session.close()


def execute(cmd, timeout=360, session=None):
    """
    Execute command in guest or host, if session is not None return
    command output in guest else return command output in host

    :param cmd: Shell commands
    :param timeout: Timeout to execute command
    :param session: ShellSession or None

    :return: Command output string
    """
    if session:
        ret = session.cmd_output_safe(cmd, timeout=timeout)
    else:
        ret = process.getoutput(cmd)
    target = 'guest' if session else 'host'
    LOG.debug("(%s) Execute command('%s')" % (target, cmd))
    return ret


@error_context.context_aware
def verify_clocksource(expected, session=None):
    """
    Verify if host/guest use the expected clocksource
    :param expected: Expected clocksource
    :param session: VM session
    """
    error_context.context("Check the current clocksource", LOG.info)
    cmd = "cat /sys/devices/system/clocksource/"
    cmd += "clocksource0/current_clocksource"
    return expected in execute(cmd, session=session)


@error_context.context_aware
def sync_time_with_ntp(session=None):
    """
    Sync guest or host time with ntp server
    :param session: VM session or None
    """
    error_context.context("Sync time from ntp server", LOG.info)
    cmd = "ntpdate clock.redhat.com; hwclock -w"
    return execute(cmd, session)


@error_context.context_aware
def update_clksrc(vm, clksrc=None):
    """
    Update linux guest's clocksource and re-boot guest

    :params vm: Virtual machine for vm
    :params clksrc: Expected clocksource
    """
    params = vm.get_params()
    if 'fedora' in params["os_variant"] and clksrc and clksrc != 'kvm-clock':
        cpu_model_flags = params.get["cpu_model_flags"]
        params["cpu_model_flags"] = cpu_model_flags + ",-kvmclock"

    error_context.context("Update guest kernel cli to '%s'" %
                          (clksrc or "kvm-clock"),
                          LOG.info)
    if clksrc:
        boot_option_added = "clocksource=%s" % clksrc
        utils_test.update_boot_option(vm, args_added=boot_option_added)


def is_ntp_enabled(session):
    """
    Get current NTP state for guest/host
    """
    cmd = 'timedatectl | %s "NTP enabled"' % grep_binary
    return 'yes' in execute(cmd, session=session).split(":")[1].strip()


def ntp_switch(session, off=True):
    """
    Turn off/on ntp for guest/host
    """
    cmd = "timedatectl set-ntp"
    if off:
        cmd += " 0"
    else:
        cmd += " 1"
    output = execute(cmd, session=session)
    ntp_enabled = is_ntp_enabled(session)
    if off and ntp_enabled:
        raise exceptions.TestError("Fail to switchoff ntp: %s", output)
    if not off and not ntp_enabled:
        raise exceptions.TestError("Fail to switchon ntp: %s", output)
