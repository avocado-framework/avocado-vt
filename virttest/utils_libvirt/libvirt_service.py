import logging

from avocado.utils import process

from virttest import remote, utils_libvirtd
from virttest.staging import service

LOG = logging.getLogger("avocado." + __name__)


def get_service_name(params):
    """
    Get service name on source or target host

    :param params: Dictionary with the test parameters
    """
    service_name = params.get("service_name", "libvirtd")
    service_on_dst = "yes" == params.get("service_on_dst", "no")
    server_ip = params.get("remote_ip")
    server_user = params.get("remote_user", "root")
    server_pwd = params.get("remote_pwd")

    s_name = None
    if service_name == "libvirtd":
        if service_on_dst:
            remote_session = remote.wait_for_login(
                "ssh", server_ip, "22", server_user, server_pwd, r"[\#\$]\s*$"
            )
            s_name = utils_libvirtd.Libvirtd(session=remote_session).service_name
            remote_session.close()
        else:
            s_name = utils_libvirtd.Libvirtd().service_name
    else:
        s_name = service_name
    LOG.debug("service name: %s", s_name)
    return s_name


def kill_service(params):
    """
    Kill service on source or target host

    :param params: Dictionary with the test parameters
    """
    service_on_dst = "yes" == params.get("service_on_dst", "no")

    service_name = get_service_name(params)
    cmd = "kill -9 `pidof %s`" % service_name
    if service_on_dst:
        remote.run_remote_cmd(cmd, params, ignore_status=False)
    else:
        process.run(cmd, ignore_status=False, shell=True)


def control_service(params):
    """
    Control service on source or target host

    :param params: Dictionary with the test parameters
    """
    service_on_dst = "yes" == params.get("service_on_dst", "no")
    service_operations = params.get("service_operations", "restart")
    server_ip = params.get("remote_ip")
    server_user = params.get("remote_user", "root")
    server_pwd = params.get("remote_pwd")

    service_name = get_service_name(params)
    if service_on_dst:
        remote_runner = remote.RemoteRunner(
            host=server_ip, username=server_user, password=server_pwd
        )
        runner = remote_runner.run
    else:
        runner = process.run
    control_service = service.Factory.create_service(service_name, run=runner)
    if service_operations == "restart":
        control_service.restart()
    elif service_operations == "stop":
        if service.status():
            control_service.stop()


def ensure_service_status(service_name, expect_active=True):
    """
    Operate the service to expected state

    :param service_name: str, service name to be operated
    :param expect_active: bool, True when expected state is active,
                                False when expected state is inactive
    :return: True if service was active when checking, False if not
    """
    srvc = service.Factory.create_service(service_name)
    status = srvc.status()
    LOG.debug(
        f'Current service status of {service_name} is {"active" if status else "inactive"}'
    )
    if not status and expect_active:
        LOG.debug(f"Starting service {service_name}")
        srvc.start()
    if status and not expect_active:
        LOG.debug(f"Stopping service {service_name}")
        srvc.stop()
    return status
