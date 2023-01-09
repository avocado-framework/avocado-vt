"""
libvirt audit related utility functions
"""

from avocado.utils import process
from avocado.utils import service

from virttest import utils_libvirtd


def enable_audit_log(libvirtd_config, audit_level=1):
    """
    Configure audit log level

    :param libvirtd_config: libvirtd config object
    :param audit_level: audit level
    """
    libvirtd_config.audit_level = audit_level
    libvirtd_config.audit_logging = 1
    utils_libvirtd.Libvirtd('virtqemud').restart()


def clean_up_audit_log_file():
    """
    Clean up audit message in log file.
    """
    cmd = "truncate -s 0  /var/log/audit/audit.log*"
    process.run(cmd, shell=True)


def ensure_auditd_started():
    """
    Check audit service status and start it if it's not running
    """
    service_name = 'auditd'
    service_mgr = service.ServiceManager()
    status = service_mgr.status(service_name)
    if not status:
        service_mgr.start(service_name)
