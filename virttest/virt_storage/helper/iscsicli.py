import re

from avocado.utils import genio
from avocado.utils import process
from avocado.utils import service


def get_pool_helper(pool):
    host = pool.source.hosts[0].hostname
    port = pool.source.hosts[0].port or 3260
    target = pool.source.devices[0].path
    initiator = pool.source.initiator
    auth = pool.source.auth
    return IscsiCli(host, port, target, initiator, auth)


class IscsiCli(object):
    dev_root = '/dev/disk/by-path/'
    initiator_file = "/etc/iscsi/initiatorname.iscsi"
    iscsi_service = service.SpecificServiceManager("iscsi")

    def __init__(self, host, port=3260,
                 target=None, initiator=None, auth=None):
        self.portal = "%s:%s" % (host, port)
        self.target = target
        self.initiator = initiator
        self.auth = auth
        self._is_logged_in = False
        if self.auth:
            if self.auth.type == "chap":
                cmd = ("iscsiadm -m node --targetname %s -p %s -o update -n discovery.sendtargets.auth.authmethod"
                       " -v %s" % (self.target, self.portal, "CHAP"))
                process.system(cmd, shell=True, verbose=True)
                if self.auth.username:
                    cmd = "iscsiadm -m node --targetname %s -p %s -o update -n node.session.auth.username -v %s" % (
                        self.target, self.portal, self.auth.username)
                    process.system(cmd, shell=True, verbose=True)
                if self.auth.password:
                    cmd = "iscsiadm -m node --targetname %s -p %s -o update -n node.session.auth.password -v %s" % (
                        self.target, self.portal, self.auth.password)
                    process.system(cmd, shell=True, verbose=True)
        if self.initiator:
            context = "InitiatorName=%s" % self.initiator
            genio.write_one_line(self.initiator_file, context)
        self.iscsi_service.restart()

    def discovery_all_targets(self):
        targets = list()
        cmd = "iscsiadm -m discovery --type sendtargets -p %s" % self.portal
        for line in process.system_output(
                cmd, shell=True, verbose=True).splitlines():
            target = line.split()[1]
            targets.append(target)
        return targets

    def login(self):
        if not self.is_logged:
            targets = self.discovery_all_targets()
            if self.target is None and targets:
                self.target = targets[0]
            assert self.target in self.discovery_all_targets(
            ), "No target '%s' not discovey" % self.target
            cmd = "iscsiadm -m node --targetname %s -p %s -l" % (
                self.target, self.portal)
            process.system(cmd, shell=True, verbose=True)
            self._is_logged_in = True

    def list_disks(self):
        self.login()
        cmd = "ls %s" % self.dev_root
        dev_regex = r"ip-%s-iscsi-%s-lun-\d+" % (self.portal, self.target)
        output = process.system_output(cmd, shell=True, verbose=True)
        dev_pattern = re.compile(dev_regex, re.M | re.I)
        return map(lambda x: "%s/%s" %
                             (self.dev_root, x), dev_pattern.findall(output))

    def logout(self):
        if self.is_logged:
            cmd = "iscsiadm -m node --targetname %s -p %s -u" % (
                self.target, self.portal)
            process.system(cmd, shell=True, verbose=True)
            self._is_logged_in = False

    @staticmethod
    def get_size(path):
        cmd = "blockdev --getsize64 '%s'" % path
        try:
            return int(process.system_output(cmd, shell=True, verbose=True))
        except process.CmdError:
            return 0

    def path_to_url(self, path):
        match = re.search(
            r"ip-(?P<portal>.*)-iscsi-(?P<target>.*)-lun-(?P<lun>\d+)", path)
        if match:
            portal = match.groupdict().get("portal")
            target = match.groupdict().get("target")
            lun = match.groupdict().get("lun")
            secret = ""
            if self.auth:
                if self.auth.username:
                    secret += self.auth.username
                if self.auth.password:
                    secret += ":%s" % self.auth.password
            if secret:
                secret += "@"
            return "iscsi://%s%s/%s/%s" % (secret, portal, target, lun)

        return None

    @property
    def is_logged(self):
        if self._is_logged_in is None:
            cmd = "iscsiadm -m session "
            output = process.system_output(
                cmd, shell=True, ignore_status=True, verbose=True)
            for line in output.splitlines():
                if self.portal in line and self.target in line:
                    self._is_logged_in = True
                    break
            else:
                self._is_logged_in = False
        return self._is_logged_in

    @property
    def capacity(self):
        return sum(map(self.get_size, self.list_disks()))
