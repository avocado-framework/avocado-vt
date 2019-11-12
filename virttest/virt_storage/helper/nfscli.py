import os
import tempfile

from avocado.utils import process

import fscli


def get_pool_helper(pool):
    target = pool.target.path
    dir_path = pool.source.dir_path
    host = pool.source.hosts[0].hostname
    return NfsCli(host, dir_path, target)


class NfsCli(fscli.FsCli):

    def __init__(self, host, dir_path, target=None):
        self.host = host
        self.export_dir = dir_path
        self._target = target
        self._is_mounted = None
        self._is_export = None
        self._protocol = r"nfs://"
        super(NfsCli, self).__init__(self.target)

    @property
    def target(self):
        if self._target is None:
            self._target = tempfile.mkdtemp()
        if not os.path.isdir(self._target):
            os.makedirs(self._target)
        return self._target

    @target.setter
    def target(self, _target):
        self._target = _target

    @property
    def src_path(self):
        return "%s:%s" % (self.host, self.export_dir)

    @property
    def is_mounted(self):
        if self._is_mounted is None:
            cmd = "grep '%s' /proc/mounts |grep %s" % (
                self.src_path, self.target)
            ret = process.system(cmd, shell=True, ignore_status=True)
            self._is_mounted = ret == 0
        return self._is_mounted

    def umount(self):
        if self.is_mounted:
            cmd = "umount -f %s" % self.target
            process.system(cmd, shell=True, ignore_status=False)
        self._is_mounted = False

    def mount(self):
        assert self.is_export, "'%s' not export in host '%s'" % (
            self.export_dir, self.host)
        if not os.path.isdir(self.target):
            os.makedirs(self.target)
        if self.is_mounted:
            return
        cmd = "mount -t nfs %s %s" % (self.src_path, self.target)
        process.system(cmd, shell=True, ignore_status=False)
        self._is_mounted = True

    def path_to_url(self, f):
        return f.replace(self.target, "%s%s" % (self._protocol, self.src_path))

    def url_to_path(self, url):
        return url.replace("%s%s" % (self._protocol, self.src_path), self.target)

    def get_url_by_name(self, name):
        return "%s%s/%s" % (self._protocol, self.src_path, name)

    @property
    def is_export(self):
        if self._is_export is None:
            cmd = "showmount --no-headers -e %s |grep %s" % (
                self.host, self.export_dir)
            ret = process.system(cmd, shell=True, ignore_status=True)
            self._is_export = ret == 0
        return self._is_export

    def remove(self):
        if self.is_mounted:
            cmd = "rm -rf %s/*" % self.target
            process.system(cmd, shell=True)
            self.umount()
        super(NfsCli, self).remove()
