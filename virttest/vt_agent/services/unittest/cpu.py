import logging
import socket

from avocado.utils import process

LOG = logging.getLogger('avocado.service.' + __name__)


def __get_cpu_info():
    cmd = "lscpu | tee"
    output = process.run(cmd, shell=True, ignore_status=True).stdout_text.splitlines()
    cpu_info = dict(map(lambda x: [i.strip() for i in x.split(":", 1)], output))
    return cpu_info


def get_vendor_id():
    hostname = socket.gethostname()
    info = __get_cpu_info()
    vendor_id = info.get("Vendor ID")
    LOG.info(f"The vendor id is {vendor_id} on the {hostname}")
    return vendor_id
