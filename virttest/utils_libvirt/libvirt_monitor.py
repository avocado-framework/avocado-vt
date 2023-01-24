import copy
import logging

from avocado.core import exceptions

from virttest import virsh

LOG = logging.getLogger("avocado." + __name__)


def check_domjobinfo(vm_name, expected_dict, remote=False, remote_ip=None, options=""):
    """
    Check domjobinfo

    :param vm_name: vm name
    :param expected_dict: the dict for expected domain job info
    :param remote: check remote host if remote is True
    :param remote_ip: the ip of remote host
    :param options: the options of domjobinfo command
    """
    LOG.info("Check domjobinfo")
    if remote:
        dest_uri = "qemu+ssh://%s/system" % remote_ip
        jobinfo = virsh.domjobinfo(vm_name, options, debug=True, uri=dest_uri)
    else:
        jobinfo = virsh.domjobinfo(vm_name, options, debug=True)
    tmp_dict = copy.deepcopy(expected_dict)
    for line in jobinfo.stdout.splitlines():
        key = line.split(":")[0]
        if key in tmp_dict:
            value = ":".join(line.strip().split(":")[1:]).strip()
            LOG.debug("domjobinfo: key = %s, value = %s", key, value)
            LOG.debug("expected key = %s, value = %s", key, tmp_dict.get(key))
            if value != tmp_dict.get(key):
                raise exceptions.TestFail(
                    "'%s' is not matched expect '%s'" % (value, tmp_dict.get(key))
                )
            else:
                del tmp_dict[key]
