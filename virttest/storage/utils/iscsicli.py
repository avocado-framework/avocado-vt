import re
import infi.iscsiapi

from avocado.utils import process


software_initiator = infi.iscsiapi.get_iscsi_software_initiator()
if not software_initiator.is_installed():
    software_initiator.install()


class IscsiCli(object):

    API = infi.iscsiapi.get_iscsiapi()
    dev_root = '/dev/disk/by-path'

    def __init__(self, host, port='3260', initiator=None, target=None):
        if initiator:
            if self.API.get_source_iqn() != initiator:
                API.reset_source_iqn(initiator)
        self.host = host
        self.port = port
        self.target = target
        self.initiator = initiator
        self.portal = ":".join([host, port])

    def discover(self):
        return self.API.discover(ip_address=self.host)

    def get_discovered_targets(self):
        return self.API.get_discovered_targets()

    def get_target_obj(self):
        self.discover()
        for target in self.get_discovered_targets():
            if target.get_iqn() == self.target:
                return target
        return None

    def login(self):
        self.logout()
        target = self.get_target_obj()
        for endpoint in target.get_endpoints():
            ip_address = endpoint.get_ip_address()
            if self.host == ip_address:
                return self.API.login(target, endpoint)
        return self.API.login_all(target)

    def list_luns(self):
        self.login()
        cmd = "ls %s" % self.dev_root
        output = process.system_output(cmd, shell=True, ignore_status=True)
        disks = output.split()
        regex_str = ".*".join([self.portal, self.target, r"-lun-(\d+)$"])
        pattern = re.compile(regex_str)
        matched = filter(None, map(lambda x: pattern.search(x), disks))
        return map(lambda x: int(x.group(0)), matched)

    def logout(self):
        target = self.get_target_obj()
        self.API.logout_all(target)
